FROM nginx:alpine

# O healthcheck do Compose precisa de um cliente HTTP dentro do contêiner.
# A imagem base não traz um de forma confiável, e depender disso já custou uma
# rodada de CI: o healthcheck falhava sem sequer registrar acesso no nginx.
RUN apk add --no-cache curl

COPY nginx.conf /etc/nginx/conf.d/default.conf
