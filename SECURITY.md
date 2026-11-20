# Segurança

## Estado do protótipo

O FluxoFiscal é uma prova de conceito acadêmica. A autenticação é
deliberadamente simplificada (ADR-0011): a identidade é autodeclarada pelo
e-mail enviado em cada requisição, e nenhum serviço verifica quem faz a
chamada. Não use esta aplicação com dados reais de terceiros.

Na implantação de demonstração, a borda pública (`app/deploy/Caddyfile`)
recusa as rotas destrutivas de outros usuários, as rotas internas
(`/_interno/`), o registro de consumo (`POST /billing/usage`) e a
documentação automática da API. Veja `app/deploy/README.md`.

## Segredos

- Nenhum segredo é versionado. Chaves e senhas ficam só no `.env` de cada
  máquina, que o `.gitignore` exclui; o `app/.env.example` traz apenas
  valores de desenvolvimento assumidamente inseguros.
- Na VPS, o `app/deploy/instalar.sh` gera segredos novos e aleatórios na
  primeira instalação.
- O hook `.githooks/pre-commit` roda o gitleaks nos arquivos de cada commit
  (`git config core.hooksPath .githooks` para ativar).

## Como reportar uma falha

Abra um aviso privado em **Security → Report a vulnerability** neste
repositório, sem publicar detalhes em issue aberta.
