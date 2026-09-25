# pdf

Aplicação web para converter imagens em PDF, com suporte a:

- múltiplas imagens (até 10), com reordenação arrastando as miniaturas
- página A4 (com margem configurável) ou tamanho original
- qualidade máxima (sem perda), equilibrada ou arquivo mínimo
- mesclar tudo em um PDF (`imagens_para_pdf.pdf`) ou um PDF por imagem
  (com o nome original da imagem)
- limite de 10 MB por imagem e 100 MB no total

Acesso protegido por login via Keycloak (SSO); usuário e senha locais
(mesma tela do `ia`, sem TOTP) continuam como plano B.

## Estrutura do repositório

```text
pdf/
├── app/
│   ├── main.py
│   ├── converter.py
│   └── templates/
│       ├── index.html
│       └── login.html
├── applications/
│   └── argocd.pdf.yaml            # Application do Argo CD
├── k8s/
│   ├── pdf.yaml                   # Namespace, Deployment, Service, Ingress
│   ├── pdf-auth-secrets.sealed.yaml  # usuário + hash da senha local (selado, fallback)
│   └── pdf-oidc.sealed.yaml       # client secret + cookie secret do oauth2-proxy (selado)
├── build.sh                       # builda a imagem e importa no containerd do k0s
├── change-password.sh             # define/troca o usuário e a senha de login local
├── Dockerfile
├── requirements.txt
└── README.md
```

## Rodando no cluster (homelab)

Pré-requisitos: ArgoCD, Sealed Secrets, `ingress-nginx` e `cert-manager`
instalados (repositórios de mesmo nome) e DNS `pdf.diegofnunesbr.com`
apontando pro node (repositório `dns`).

Na `vm-ubuntu` (é lá que o `docker build` e o `k0s ctr` precisam rodar):

```bash
git clone https://github.com/diegofnunesbr/pdf.git
cd pdf
./build.sh
kubectl apply -f applications/argocd.pdf.yaml
```

Acesse `https://pdf.diegofnunesbr.com`. O `Ingress` já libera upload de
até 100 MB (`proxy-body-size`), igual ao `MAX_TOTAL_MB` padrão - se mudar
um, mude o outro.

**Lembrete:** a Application aponta pro GitHub, não pro clone local -
mudança em `k8s/` só tem efeito depois de `git push`. Imagem nova (mesma
tag `local`) não é detectada pelo Argo CD: depois do `./build.sh`, rode
`kubectl -n pdf rollout restart deployment/pdf`.

## Login pelo Keycloak (SSO)

Um sidecar [`oauth2-proxy`](https://oauth2-proxy.github.io/oauth2-proxy/)
autentica contra o realm `home` do Keycloak (repositório `keycloak`,
`https://keycloak.diegofnunesbr.com`) antes de qualquer requisição chegar
no app - mesmo padrão do repositório `rundeck`. Só quem estiver no grupo
`pdf-users` do Keycloak entra (`--allowed-group`).

Como o `pdf` tem login próprio (usuário/senha, ver seção abaixo), em vez
de empilhar os dois logins o `app/main.py` foi ajustado pra confiar no
usuário já autenticado pelo proxy: quando a requisição chega com o header
`X-Forwarded-Preferred-Username` (só o oauth2-proxy pode setar esse
header - ele fala com o app em `127.0.0.1`, não exposto por fora do pod),
a tela de login local nem aparece. "Sair" nesse caso também derruba a
sessão no Keycloak (`PROXY_LOGOUT_URL`), não só a sessão local.

Pra dar acesso a alguém: no Keycloak, realm `home`, coloque o usuário no
grupo `pdf-users`.

## Login local (plano B)

Usuário e hash bcrypt da senha ficam em `k8s/pdf-auth-secrets.sealed.yaml`,
aplicado pelo Argo CD. Só é usado se o Keycloak cair (acesso via a porta
`8000` direta da Service, sem passar pelo oauth2-proxy - não exposta pelo
Ingress). Pra definir (primeira vez, ou num cluster novo com outra chave
do Sealed Secrets) ou trocar a senha, rode do seu clone (precisa de
`htpasswd`, `kubeseal` e do contexto `k0s`, ver README do repositório
`argocd`, seção "Acessar o cluster de fora da VM"):

```bash
./change-password.sh
```

Pede usuário e senha (sem ecoar), sela, faz commit + push, espera o Argo CD
sincronizar e reinicia o pod. A sessão dura 30 dias; reiniciar o pod
desloga (as sessões ficam em memória).

## Rodando fora do cluster

O app não sobe sem `AUTH_USERNAME` e `AUTH_PASSWORD_HASH`. Gere um hash
(`printf '%s' 'senha' | htpasswd -niBC 10 "" | tr -d ':\n' | sed 's/^\$2y/\$2b/'`)
e:

```bash
pip install -r requirements.txt
AUTH_USERNAME=eu AUTH_PASSWORD_HASH='<hash>' uvicorn app.main:app --reload
```

Acesse `http://localhost:8000`.

Com Docker:

```bash
docker build -t pdf .
docker run -d -p 8000:8000 --restart unless-stopped --name pdf \
  -e AUTH_USERNAME=eu -e AUTH_PASSWORD_HASH='<hash>' pdf
docker logs -f pdf
docker rm -f pdf
```

## Tecnologias

- Python, FastAPI, Pillow, img2pdf, reportlab, bcrypt
- HTML / CSS / JS
- Docker

## Observações

- Nenhum dado é armazenado
- Processamento em memória

## Variáveis de ambiente

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `AUTH_USERNAME` | - | Usuário de login (**obrigatório**) |
| `AUTH_PASSWORD_HASH` | - | Hash bcrypt da senha (**obrigatório**) |
| `MAX_FILE_SIZE_MB` | 10 | Tamanho máximo por imagem (MB) |
| `MAX_TOTAL_MB` | 100 | Tamanho total máximo (MB) |
| `A4_MAX_MARGIN_MM` | 100 | Margem máxima para A4 (mm) |
