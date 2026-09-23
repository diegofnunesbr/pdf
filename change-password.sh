#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

NODE="${NODE:-diegofnunesbr@192.168.0.4}"
KCTL="kubectl --context=Default"
SEALED=k8s/pdf-auth-secrets.sealed.yaml

CURRENT_USER=$(ssh "$NODE" "$KCTL -n pdf get secret pdf-auth-secrets -o jsonpath='{.data.username}' 2>/dev/null | base64 -d" || true)
read -rp "Usuário [${CURRENT_USER:-diegofnunesbr}]: " USERNAME
USERNAME="${USERNAME:-${CURRENT_USER:-diegofnunesbr}}"
read -rsp "Nova senha: " PW; echo
read -rsp "Confirme a senha: " PW2; echo
[ -n "$PW" ] && [ "$PW" = "$PW2" ] || { echo "Senhas vazias ou diferentes."; exit 1; }

HASH=$(printf '%s' "$PW" | htpasswd -niBC 10 "" | tr -d ':\n' | sed 's/^\$2y/\$2b/')

git pull --ff-only

CERT=$(mktemp)
trap 'rm -f "$CERT"' EXIT
ssh "$NODE" "kubeseal --fetch-cert --controller-name sealed-secrets --controller-namespace kube-system" > "$CERT"

cat <<EOF | kubeseal --cert "$CERT" --scope cluster-wide --format yaml > "$SEALED"
apiVersion: v1
kind: Secret
metadata:
  name: pdf-auth-secrets
  namespace: pdf
type: Opaque
data:
  username: $(printf '%s' "$USERNAME" | base64 -w0)
  password-hash: $(printf '%s' "$HASH" | base64 -w0)
EOF

git add "$SEALED"
git commit -m "rotate pdf login password"
git push

REV=$(git rev-parse HEAD)
ssh "$NODE" "$KCTL -n argocd annotate application pdf argocd.argoproj.io/refresh=hard --overwrite" >/dev/null
echo "Aguardando o Argo CD sincronizar $REV..."
for _ in $(seq 1 60); do
  STATUS=$(ssh "$NODE" "$KCTL -n argocd get application pdf -o jsonpath='{.status.sync.status} {.status.sync.revision}'")
  [[ "$STATUS" == "Synced $REV" ]] && break
  sleep 5
done
[[ "$STATUS" == "Synced $REV" ]] || { echo "Timeout esperando o sync. Rode o restart manualmente depois."; exit 1; }

sleep 5
ssh "$NODE" "$KCTL -n pdf rollout restart deployment/pdf && $KCTL -n pdf rollout status deployment/pdf --timeout=300s"
echo "Pronto. Login em https://pdf.diegofnunesbr.com"
