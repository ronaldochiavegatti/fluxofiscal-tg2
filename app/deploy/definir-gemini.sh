#!/usr/bin/env bash
# Grava (ou troca) a GEMINI_API_KEY no .env da VPS e reinicia quem usa IA.
# A chave é digitada escondida e não aparece no histórico do shell.
#
#   ssh -t root@<IP> bash /opt/fluxofiscal/deploy/definir-gemini.sh
set -euo pipefail
cd "$(dirname "$0")/.."

read -r -s -p "Cole a GEMINI_API_KEY e tecle Enter: " K; echo
[ -n "$K" ] || { echo "Nada digitado; .env não foi alterado."; exit 1; }

sed -i "s|^GEMINI_API_KEY=.*|GEMINI_API_KEY=$K|" .env
# --force-recreate: o env_file só é relido ao recriar o contêiner. O agent,
# ao subir, vetoriza a base de conhecimento que ficou sem embedding.
docker compose up -d --force-recreate --wait documents agent worker
echo "Chave gravada. documents, agent e worker reiniciados."
