import logging
import os
import secrets
import threading
import time
from pathlib import Path

import bcrypt
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from app.converter import images_to_pdf

logging.getLogger("img2pdf").setLevel(logging.ERROR)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

app = FastAPI()


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        parsed = int(value)
        return parsed if parsed > 0 else default
    except ValueError:
        return default


A4_MAX_MARGIN_MM = _env_int("A4_MAX_MARGIN_MM", 100)
MAX_FILE_SIZE_MB = _env_int("MAX_FILE_SIZE_MB", 10)
MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024
MAX_TOTAL_MB = _env_int("MAX_TOTAL_MB", 100)
MAX_TOTAL_SIZE = MAX_TOTAL_MB * 1024 * 1024

stats = {"conversions": 0, "images": 0}
_stats_lock = threading.Lock()

_INDEX_HTML_PATH = Path(__file__).parent / "templates" / "index.html"
_LOGIN_HTML_PATH = Path(__file__).parent / "templates" / "login.html"

AUTH_USERNAME = os.environ.get("AUTH_USERNAME")
AUTH_PASSWORD_HASH = os.environ.get("AUTH_PASSWORD_HASH")
if not AUTH_USERNAME or not AUTH_PASSWORD_HASH:
    raise RuntimeError("AUTH_USERNAME e AUTH_PASSWORD_HASH precisam estar definidos")

SESSION_COOKIE = "pdf_session"
SESSION_TTL_SECONDS = 30 * 24 * 60 * 60
PUBLIC_PATHS = {"/health", "/login", "/favicon.ico"}

_sessions: dict[str, float] = {}
_sessions_lock = threading.Lock()


def _valid_session(token: str | None) -> bool:
    if not token:
        return False
    with _sessions_lock:
        expires_at = _sessions.get(token)
        if expires_at is None:
            return False
        if expires_at < time.time():
            del _sessions[token]
            return False
        return True


def _check_credentials(username: str, password: str) -> bool:
    user_ok = secrets.compare_digest(username.encode(), AUTH_USERNAME.encode())
    password_ok = bcrypt.checkpw(password.encode(), AUTH_PASSWORD_HASH.encode())
    return user_ok and password_ok


@app.middleware("http")
async def require_login(request: Request, call_next):
    if request.url.path in PUBLIC_PATHS or _valid_session(request.cookies.get(SESSION_COOKIE)):
        return await call_next(request)
    if request.method == "GET":
        return RedirectResponse("/login", status_code=303)
    return JSONResponse({"detail": "Sessão expirada, faça login de novo."}, status_code=401)


def _login_html(error: str = "") -> str:
    raw = _LOGIN_HTML_PATH.read_text(encoding="utf-8")
    error_html = f'<p class="login-error">{error}</p>' if error else ""
    return raw.replace("__ERROR__", error_html)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if _valid_session(request.cookies.get(SESSION_COOKIE)):
        return RedirectResponse("/", status_code=303)
    return HTMLResponse(content=_login_html())


@app.post("/login")
async def login(username: str = Form(...), password: str = Form(...)):
    if not _check_credentials(username, password):
        return HTMLResponse(content=_login_html("Usuário ou senha inválidos."), status_code=401)
    token = secrets.token_hex(32)
    with _sessions_lock:
        _sessions[token] = time.time() + SESSION_TTL_SECONDS
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=True,
        samesite="lax",
    )
    return response


@app.get("/logout")
async def logout(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        with _sessions_lock:
            _sessions.pop(token, None)
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response


def _index_html() -> str:
    raw = _INDEX_HTML_PATH.read_text(encoding="utf-8")
    return (
        raw.replace("__MAX_FILE_SIZE_MB__", str(MAX_FILE_SIZE_MB))
        .replace("__MAX_TOTAL_MB__", str(MAX_TOTAL_MB))
        .replace("__A4_MAX_MARGIN_MM__", str(A4_MAX_MARGIN_MM))
    )


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/metrics")
async def metrics():
    return stats


@app.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(content=_index_html())


@app.post("/convert")
async def convert(
    files: list[UploadFile] = File(...),
    page_size: str = Form(...),
    margin: str = Form("0"),
    quality: str = Form("high"),
):

    total_size = 0
    file_streams = []

    for f in files:

        if not f.content_type or not f.content_type.startswith("image/"):
            raise HTTPException(400, "Arquivo não suportado")

        content = await f.read()

        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                400,
                f"Arquivo muito grande. Máximo {MAX_FILE_SIZE_MB} MB por imagem.",
            )

        total_size += len(content)

        if total_size > MAX_TOTAL_SIZE:
            raise HTTPException(
                400,
                f"Tamanho total excede {MAX_TOTAL_MB} MB."
            )

        f.file.seek(0)
        file_streams.append(f.file)

    margin_mm = int(margin) if margin and str(margin).isdigit() else 0

    if page_size == "A4" and margin_mm > A4_MAX_MARGIN_MM:
        raise HTTPException(
            400,
            f"Margem muito grande para A4. Use no máximo {A4_MAX_MARGIN_MM} mm.",
        )

    logger.info(f"Convertendo {len(files)} imagens")

    try:

        pdf = images_to_pdf(
            files=file_streams,
            page_size=page_size,
            margin_mm=margin_mm,
            quality=quality.strip().lower(),
        )

        with _stats_lock:
            stats["conversions"] += 1
            stats["images"] += len(files)

    except (ValueError, Exception) as e:
        msg = str(e).lower()

        if "dimension" in msg:
            raise HTTPException(
                400,
                "Imagem com resolução muito grande.",
            )

        logger.exception("Error converting images to PDF")
        raise HTTPException(500, "Erro ao converter imagens.")

    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="imagens_para_pdf.pdf"'
        },
    )
