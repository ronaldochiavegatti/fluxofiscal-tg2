# Frontend de produção para o deploy na VPS: build estático do Vite servido por
# nginx. O Dockerfile de dev (services/frontend/Dockerfile) roda `vite dev`,
# que recusa hosts desconhecidos (Vite >= 5.4.12) e não serve para expor.
#
# As VITE_* são lidas no build, não em tempo de execução: mudar o domínio
# exige `docker compose build frontend`.

FROM node:20-alpine AS build
WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

ARG VITE_API_BASE_URL
ARG VITE_UNLEASH_FRONTEND_URL
ARG VITE_UNLEASH_FRONTEND_TOKEN
ARG VITE_UNLEASH_APP_NAME=fluxofiscal
ARG VITE_VISUAL_NOVO=true
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_UNLEASH_FRONTEND_URL=$VITE_UNLEASH_FRONTEND_URL \
    VITE_UNLEASH_FRONTEND_TOKEN=$VITE_UNLEASH_FRONTEND_TOKEN \
    VITE_UNLEASH_APP_NAME=$VITE_UNLEASH_APP_NAME \
    VITE_VISUAL_NOVO=$VITE_VISUAL_NOVO

RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
# SPA: qualquer rota desconhecida (/dashboard, /documents/42...) cai no
# index.html e o React Router resolve. Assets com hash ficam em cache longo.
RUN printf '%s\n' \
  'server {' \
  '  listen 80;' \
  '  root /usr/share/nginx/html;' \
  '  location /assets/ { expires 1y; add_header Cache-Control "public, immutable"; }' \
  '  location / { try_files $uri $uri/ /index.html; add_header Cache-Control "no-cache"; }' \
  '}' > /etc/nginx/conf.d/default.conf
EXPOSE 80
