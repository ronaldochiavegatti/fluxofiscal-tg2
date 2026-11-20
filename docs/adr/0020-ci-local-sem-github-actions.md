# ADR-0020 — Portões locais como fonte da verdade, sem GitHub Actions

- **Data:** 2026-09-12
- **Estado:** Aceita

## Contexto

Em 12/09/2026, a conta que hospeda o repositório passou a ter jobs do GitHub
Actions recusados com `"The job was not started because recent account
payments have failed or your spending limit needs to be increased"`. O
sintoma variou: em alguns runs, todos os jobs falharam ao subir; em outros
(ex.: o run da US-28, `#67`), a matriz inteira de backend, o `Integração
(docker compose)` e o `Smoke de carga (k6)` completaram normalmente, e só o
job agregador `CI aprovada` — o último da cadeia — foi recusado, aparentemente
por esgotar a cota no meio da execução.

O repositório é privado, no plano GitHub Free. Duas descobertas fecharam a
decisão:

1. **GitHub Actions é a única coisa afetada.** Hospedagem de repositório
   privado, Pull Requests, Issues, histórico de commits e GHCR (dentro da
   cota) continuam gratuitos e ilimitados, independente de cobrança de Actions.
2. **Proteção de branch exige GitHub Pro ou repositório público.** A API
   devolveu `"Upgrade to GitHub Pro or make this repository public to enable
   this feature"` ao consultar a proteção da `main`. Ou seja: mesmo antes deste
   incidente, **nada no GitHub jamais impediu tecnicamente um merge com CI
   vermelha** neste repositório — "nunca mergear com CI vermelha"
   (`.claude/PLAYBOOK.md`) sempre foi disciplina do autor, não uma trava da
   plataforma. Ver `docs/versionamento.md` §3, já registrado antes deste ADR.

Diante disso, perseguir uma correção de cobrança (ou um runner self-hosted,
avaliado e descartado nesta mesma sessão) para manter a CI verde teria custo
de manutenção sem mudar a garantia real: o merge sempre dependeu de alguém
olhar o resultado dos portões antes de apertar o botão.

## Decisão

**Desativar GitHub Actions** no repositório
(`PUT /repos/.../actions/permissions`, `enabled: false`). Os workflows em
`.github/workflows/` continuam versionados — nada foi apagado — mas nenhum
dispara.

**Os portões da Definição de Concluído (`CLAUDE.md`, `docs/BACKLOG.md`)
passam a rodar localmente, e o registro de que rodaram vira o corpo do
commit**, não mais um artefato de CI:

- `ruff check`, `ruff format --check`, `mypy`, `pytest --cov` por serviço
  tocado; `mutmut` ao mexer em `dominio/`; portões do frontend
  (`tsc`, `eslint`, `vitest`, `build`); `docker compose up --wait` quando a
  mudança for compartilhada ou de infraestrutura.
- O commit (ou a descrição do PR) que fecha a história cita o resultado real
  — quantos testes, cobertura obtida, se o mutmut rodou ou por que não — no
  mesmo espírito de como US-23, US-24 e US-28 já vinham documentando. Isso é o
  que substitui o log da CI como evidência de que o portão passou.
- `git push` para o GitHub continua normalmente: o histórico de commits e PRs
  é a documentação confiável do processo, com ou sem Actions.

**O que fica pausado, não descartado**, enquanto Actions estiver desligado:

- `dora.yml` — a série de métricas DORA (`docs/PLANO.md` §5.1) para de
  crescer a partir de 12/09/2026. Os números coletados antes dessa data
  continuam válidos.
- `cd.yml` — publicação de imagem no GHCR a cada commit da `main` (ADR-0014).
  A última imagem publicada por commit fica congelada; `docker-compose.yml`
  (perfil `dev`, build local) continua sendo o caminho de demonstração normal.
- Os portões que só faziam sentido em CI — Playwright ponta a ponta, Trivy,
  gitleaks, k6 noturno, verificação de contrato via Schemathesis — passam a
  ser responsabilidade de rodar manualmente antes de decisões de maior risco
  (ex.: antes da defesa), em vez de em todo PR.

**Reversão.** `PUT .../actions/permissions` com `enabled: true` liga tudo de
volta assim que a cobrança for resolvida (ou um runner self-hosted for
concluído) — nenhuma mudança de código é necessária para isso.

## Consequências

**A favor**

- Zero custo, imediato, sem depender de resolver cobrança nem manter um
  runner de pé.
- Nenhuma garantia real se perde: o merge nunca foi tecnicamente bloqueado
  pela CI neste repositório (Free privado), então a disciplina de "só
  mergear com portão verde" continua idêntica — só a fonte da verificação
  muda de log de CI para execução local documentada no commit.
- Menos ruído: para de aparecer X vermelho por falta de pagamento em todo PR,
  o que mascarava falha real de código atrás de falha de infraestrutura.

**Contra**

- A série de métricas DORA (`docs/PLANO.md` §5.1, `docs/IMPACTO-ARTIGO.md`)
  tem um corte em 12/09/2026 — o artigo precisa registrar isso como limitação
  de coleta, não apagar a tabela.
- Publicação de imagem no GHCR por commit também para; se a demonstração final
  quiser "mesma imagem que passou na CI" (ADR-0014), alguém precisa religar
  Actions antes ou publicar manualmente.
- Verificação de contrato (Schemathesis), Playwright e Trivy só rodam se
  alguém lembrar de rodar — sem o gatilho automático de todo PR, é mais fácil
  esquecer. Mitigação: citar explicitamente no corpo do commit quando algum
  desses foi pulado, para não parecer que rodou quando não rodou.

## Alternativas descartadas

**Runner self-hosted.** Chegou a ser baixado e quase configurado nesta
sessão. Resolveria o custo sem desligar Actions, mas exige o runner sempre de
pé na máquina do autor e workflows ajustados para `runs-on: self-hosted` +
shell — mais manutenção contínua do que o ganho justifica, dado que a CI não
bloqueava merge de qualquer forma. Fica registrado como opção se a coleta de
DORA/GHCR precisar voltar antes da defesa.

**Resolver a cobrança agora.** Também funcionaria, mas depende de ação
externa (cartão, limite de gasto) fora do controle da sessão de engenharia; a
decisão de quando vale pagar por isso é do autor, não uma correção técnica.

**Manter Actions ligado, ignorando o X vermelho.** Descartado: o erro de
cobrança se mistura com falha real de teste no mesmo ícone, tornando o sinal
inútil — pior que não ter CI nenhuma.
