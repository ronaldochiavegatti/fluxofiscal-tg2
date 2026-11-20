#!/usr/bin/env bash
# Instala e sobe o FluxoFiscal numa VPS Ubuntu (Hostinger KVM 2).
# Rode como root, de dentro da pasta app/:
#
#   bash deploy/instalar.sh            # primeira vez e a cada atualização
#   DOMINIO_BASE=meudominio.com.br bash deploy/instalar.sh   # domínio próprio
#
# Idempotente: na primeira execução gera o .env com segredos novos; nas
# seguintes reaproveita o .env e só reconstrói/sobe o que mudou.
set -euo pipefail

cd "$(dirname "$0")/.."
APP_DIR="$(pwd)"
log() { printf '\n\033[1;32m==> %s\033[0m\n' "$*"; }

# ---------------------------------------------------------------- Docker
if ! command -v docker >/dev/null 2>&1; then
  log "Instalando Docker"
  curl -fsSL https://get.docker.com | sh
fi
docker compose version >/dev/null

# ---------------------------------------------------------------- Swap
# 8 GB de RAM dão conta, mas o build das imagens em paralelo tem picos.
if ! swapon --show | grep -q .; then
  log "Criando 4 GB de swap"
  fallocate -l 4G /swapfile && chmod 600 /swapfile
  mkswap /swapfile >/dev/null && swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# ---------------------------------------------------------------- Firewall
# Só SSH e web. (As portas internas já estão presas em 127.0.0.1 no overlay;
# o Docker não respeita o ufw para portas publicadas.)
if command -v ufw >/dev/null 2>&1; then
  ufw allow OpenSSH >/dev/null; ufw allow 80/tcp >/dev/null
  ufw allow 443/tcp >/dev/null; ufw allow 443/udp >/dev/null
  ufw --force enable >/dev/null
fi

# ---------------------------------------------------------------- .env
if [ ! -f .env ]; then
  log "Gerando .env com segredos novos"
  rnd() { openssl rand -hex "${1:-24}"; }

  IP="$(hostname -I | awk '{print $1}')"
  if [ -n "${DOMINIO_BASE:-}" ]; then
    APP_DOMAIN="$DOMINIO_BASE"; API_DOMAIN="api.$DOMINIO_BASE"
  else
    # sslip.io resolve <qualquer-coisa>.<ip-com-traços>.sslip.io para o IP,
    # o que dá um domínio com HTTPS sem comprar nada.
    BASE="${IP//./-}.sslip.io"
    APP_DOMAIN="fluxofiscal.$BASE"; API_DOMAIN="api.fluxofiscal.$BASE"
  fi

  GEMINI="${GEMINI_API_KEY:-}"
  if [ -z "$GEMINI" ] && [ -t 0 ]; then
    read -r -s -p "GEMINI_API_KEY (Enter = modo demo sem IA): " GEMINI; echo
  fi

  MINIO_PASS="$(rnd)"; MONGO_PASS="$(rnd)"
  sed \
    -e "s|^GEMINI_API_KEY=.*|GEMINI_API_KEY=$GEMINI|" \
    -e "s|^MINIO_ROOT_PASSWORD=.*|MINIO_ROOT_PASSWORD=$MINIO_PASS|" \
    -e "s|^MINIO_KMS_SECRET_KEY=.*|MINIO_KMS_SECRET_KEY=fluxofiscal:$(openssl rand -base64 32)|" \
    -e "s|^MONGO_ROOT_PASSWORD=.*|MONGO_ROOT_PASSWORD=$MONGO_PASS|" \
    -e "s|^MONGO_URL=.*|MONGO_URL=mongodb://fiscalflow:$MONGO_PASS@mongo:27017|" \
    -e "s|^INTERNO_TOKEN=.*|INTERNO_TOKEN=$(rnd)|" \
    -e "s|^UNLEASH_API_TOKEN=.*|UNLEASH_API_TOKEN=default:development.$(rnd)|" \
    -e "s|^UNLEASH_FRONTEND_TOKEN=.*|UNLEASH_FRONTEND_TOKEN=default:development.$(rnd)|" \
    -e "s|^VITE_API_BASE_URL=.*|VITE_API_BASE_URL=https://$API_DOMAIN|" \
    .env.example > .env

  cat >> .env <<EOF

# ---------- Deploy (deploy/instalar.sh) ----------
COMPOSE_FILE=docker-compose.yml:deploy/docker-compose.deploy.yml
APP_DOMAIN=$APP_DOMAIN
API_DOMAIN=$API_DOMAIN
UNLEASH_ADMIN_TOKEN=*:*.$(rnd)
EOF
  chmod 600 .env
elif [ -n "${DOMINIO_BASE:-}" ]; then
  # Troca de domínio numa VPS já instalada: segredos e bancos ficam, só o
  # endereço muda (o frontend é reconstruído com a nova URL da API).
  log "Trocando o domínio para $DOMINIO_BASE"
  sed -i \
    -e "s|^APP_DOMAIN=.*|APP_DOMAIN=$DOMINIO_BASE|" \
    -e "s|^API_DOMAIN=.*|API_DOMAIN=api.$DOMINIO_BASE|" \
    -e "s|^VITE_API_BASE_URL=.*|VITE_API_BASE_URL=https://api.$DOMINIO_BASE|" \
    .env
fi

set -a; . ./.env; set +a

# ---------------------------------------------------------------- Subida
log "Construindo e subindo a pilha (a primeira vez leva de 10 a 20 min)"
docker compose up -d --build --wait --wait-timeout 900

# ---------------------------------------------------------------- Flags
# O Unleash da VPS nasce vazio. Liga as mesmas flags que estão ligadas no
# ambiente local da apresentação. Idempotente: criar/ligar de novo não quebra.
log "Configurando feature flags no Unleash"
FLAGS="${FLAGS:-storage-minio dashboard-v2 visual-novo metricas-configuraveis documentos-persistidos billing-tokens-reais}"
U=http://127.0.0.1:4242/api/admin/projects/default/features
H=(-H "Authorization: $UNLEASH_ADMIN_TOKEN" -H "Content-Type: application/json")
for f in $FLAGS; do
  curl -fsS -o /dev/null "${H[@]}" -X POST "$U" \
    -d "{\"name\":\"$f\",\"type\":\"release\"}" 2>/dev/null || true
  if ! curl -fsS "${H[@]}" "$U/$f/environments/development/strategies" | grep -q flexibleRollout; then
    curl -fsS -o /dev/null "${H[@]}" -X POST "$U/$f/environments/development/strategies" \
      -d "{\"name\":\"flexibleRollout\",\"parameters\":{\"rollout\":\"100\",\"stickiness\":\"default\",\"groupId\":\"$f\"}}"
  fi
  curl -fsS -o /dev/null "${H[@]}" -X POST "$U/$f/environments/development/on"
  echo "  flag ligada: $f"
done

log "Pronto"
cat <<EOF

  Aplicação:  https://$APP_DOMAIN
  API:        https://$API_DOMAIN/health

  O certificado HTTPS sai na primeira visita (pode levar ~1 min).
  Logs:       cd $APP_DIR && docker compose logs -f --tail=100 <serviço>
  Unleash UI: no seu PC, 'ssh -L 4242:127.0.0.1:4242 root@<IP>' e abra
              http://localhost:4242 (usuário admin / senha unleash4all —
              troque no primeiro acesso).
EOF
