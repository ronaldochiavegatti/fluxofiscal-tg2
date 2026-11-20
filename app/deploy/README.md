# Deploy na VPS (Hostinger KVM 2)

Pilha completa numa VPS só, com HTTPS automático. Só o Caddy (80/443) fica
exposto; Unleash, MinIO e Prometheus ficam em `127.0.0.1` (acesso por túnel SSH).

```
internet ──► Caddy :443 ──► fluxofiscal.<ip>.sslip.io      ──► frontend (nginx, build estático)
                       └─► api.fluxofiscal.<ip>.sslip.io  ──► api-gateway ──► serviços
```

| Arquivo | Papel |
| --- | --- |
| `docker-compose.deploy.yml` | Overlay sobre o compose de dev: Caddy, frontend de produção, portas fechadas, `restart` |
| `frontend.Dockerfile` | `vite build` + nginx com fallback de SPA |
| `Caddyfile` | Dois hosts → frontend e gateway, HTTPS automático |
| `instalar.sh` | Roda **na VPS**: Docker, swap, firewall, `.env` com segredos novos, sobe tudo, liga as flags |
| `enviar.ps1` | Roda **no seu PC**: empacota `app/` (inclusive o que não foi commitado) e manda por `scp` |

## Primeira vez

1. **Hostinger:** crie a VPS KVM 2 com o template **Ubuntu 24.04** (ou "Ubuntu com
   Docker"). Anote o IP e defina a senha de root (ou cadastre sua chave SSH).
2. **No seu PC** (PowerShell, na pasta `app/`):

   ```powershell
   .\deploy\enviar.ps1 -Ip <IP-DA-VPS>
   ```

3. **Na VPS:**

   ```bash
   ssh root@<IP-DA-VPS>
   cd /opt/fluxofiscal && bash deploy/instalar.sh
   ```

   O script pede a `GEMINI_API_KEY` (Enter deixa em modo demo). A primeira
   subida leva de 10 a 20 min. No fim, ele imprime o link.

   Para gravar ou trocar a chave depois (digitação escondida):

   ```powershell
   ssh -t root@<IP-DA-VPS> bash /opt/fluxofiscal/deploy/definir-gemini.sh
   ```

> **Imagem do MinIO:** a MinIO retirou as imagens públicas (a tag
> `quay.io/minio/minio:RELEASE.2025-04-08T15-41-24Z` responde 401). O compose usa
> `bitnamilegacy/minio:2025.4.8`, o mesmo build, que ainda é baixável; numa VPS
> que já tinha a imagem antiga, o `instalar.sh` só recria o contêiner, com o
> mesmo volume e os mesmos dados.

## Atualizar depois de mudar o código

Repita os passos 2 e 3. O `.env` e os bancos da VPS são preservados; o
`docker compose up --build` só reconstrói o que mudou.

## Domínio próprio (opcional)

Na zona DNS do domínio, crie registros A para `@`, `api` e `www` apontando
para o IP da VPS. **Espere o DNS resolver** (`nslookup api.seudominio`) antes
de trocar: se o Caddy tentar emitir o certificado antes disso, o Let's Encrypt
conta falhas e pode bloquear o domínio por uma hora. Depois rode:

```bash
DOMINIO_BASE=seudominio bash deploy/instalar.sh
```

Funciona tanto numa VPS nova quanto numa já instalada: os segredos e os bancos
são mantidos, e o frontend é reconstruído com a nova URL da API. O `www`
redireciona para o domínio principal.

## Operação

```bash
cd /opt/fluxofiscal
docker compose ps                         # estado
docker compose logs -f --tail=100 agent   # logs de um serviço
docker compose restart documents          # reiniciar um serviço
```

Unleash, Prometheus e o console do MinIO, do seu PC:

```bash
ssh -L 4242:127.0.0.1:4242 -L 9090:127.0.0.1:9090 -L 9001:127.0.0.1:9001 root@<IP>
# http://localhost:4242 (admin / unleash4all — troque no primeiro acesso)
```

## Cuidados

- Quem tiver o link usa a sua `GEMINI_API_KEY`. Acompanhe o consumo no Google
  AI Studio; para cortar o uso de IA sem derrubar nada, crie e ligue a flag
  `ops-desligar-gemini` no Unleash.
- A VPS nasce com bancos vazios: crie a conta de demonstração antes da
  apresentação e teste o fluxo inteiro (upload, dashboard, chat).
- Mudar o domínio exige rebuild do frontend (as `VITE_*` entram no build).

## Rotas bloqueadas na borda pública

O protótipo não tem autenticação, então o `Caddyfile` recusa com 403, só na
VPS (o ambiente local não passa pelo Caddy):

| Rota | Por quê |
| --- | --- |
| `*/reset*` de qualquer e-mail que não seja `demo@mei.com` | apagaria dados de outro usuário; o botão "resetar dados" do painel continua funcionando para o usuário da demonstração |
| `*/_interno/*` | rotas operacionais, só para a rede interna do Docker |
| `POST /billing/usage` | quem registra consumo são os serviços, pela rede interna; o extrato (GET) segue aberto |
| `*/docs`, `*/redoc`, `*/openapi.json` | documentação automática do FastAPI, que entrega o mapa das rotas |

Para aplicar uma mudança só no Caddyfile, sem rebuild: copie o arquivo para
`/opt/fluxofiscal/deploy/` e rode `docker compose exec caddy caddy reload --config /etc/caddy/Caddyfile`.
