# Image to PDF

Aplicação web para converter imagens em PDF, com suporte a:

- múltiplas imagens
- reordenação
- A4 / Original
- margens
- qualidade máxima (sem perda)
- arquivo menor
- limite de 10 MB por imagem

## Estrutura do repositório

```text
image-to-pdf/
├── app/
│   ├── main.py
│   ├── converter.py
│   └── templates/
│       └── index.html
├── applications/
│   └── argocd.image-to-pdf.yaml   # Application do Argo CD
├── image-to-pdf.yaml              # Namespace, Deployment, Service, Ingress
├── build.sh                       # builda a imagem e importa no containerd do k0s
├── Dockerfile
├── requirements.txt
└── README.md
```

## Rodando no cluster (homelab)

Pré-requisitos: ArgoCD, `ingress-nginx` e `cert-manager` instalados
(repositórios de mesmo nome) e DNS `image-to-pdf.diegofnunesbr.com`
apontando pro node (repositório `dns`).

Na `vm-ubuntu` (é lá que o `docker build` e o `k0s ctr` precisam rodar):

```bash
git clone https://github.com/diegofnunesbr/image-to-pdf.git
cd image-to-pdf
./build.sh
kubectl apply -f applications/argocd.image-to-pdf.yaml
```

Acesse `https://image-to-pdf.diegofnunesbr.com`. O `Ingress` já libera
upload de até 100 MB (`proxy-body-size`), igual ao `MAX_TOTAL_MB` padrão -
se mudar um, mude o outro.

**Lembrete:** a Application aponta pro GitHub, não pro clone local -
mudança em `image-to-pdf.yaml` só tem efeito depois de `git push`. Imagem
nova (mesma tag `local`) não é detectada pelo Argo CD: depois do
`./build.sh`, rode `kubectl -n image-to-pdf rollout restart deployment/image-to-pdf`.

## Rodando fora do cluster

Acesse: http://localhost:8000

## Como rodar localmente

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Tecnologias

- Python
- FastAPI
- Pillow
- img2pdf
- HTML / CSS / JS
- Docker

## Observações

- Nenhum dado é armazenado
- Processamento em memória

## Variáveis de ambiente

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `MAX_FILE_SIZE_MB` | 10 | Tamanho máximo por imagem (MB) |
| `MAX_TOTAL_MB` | 100 | Tamanho total máximo (MB) |
| `A4_MAX_MARGIN_MM` | 100 | Margem máxima para A4 (mm) |

## Como rodar com Docker

```bash
docker build -t image-to-pdf .
docker run -d -p 8000:8000 \
  --restart unless-stopped \
  --name image-to-pdf \
  image-to-pdf
```

## Consultar os logs

```bash
docker logs -f image-to-pdf
```

## Parar e remover o container

```bash
docker rm -f image-to-pdf
```
