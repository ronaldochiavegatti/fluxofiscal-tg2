# ADR-0008 — Unleash auto-hospedado para feature flags

- **Data:** 2026-08-22
- **Estado:** Aceita

## Contexto

O ADR-0002 escolheu trunk-based development: mudanças pequenas integradas na
`main` várias vezes por dia. Isso cria um problema imediato — como integrar
código de uma funcionalidade que ainda não está pronta, sem expor um dashboard
pela metade ao usuário?

O plano também tem entregas genuinamente arriscadas. Trocar o pipeline de OCR
síncrono pelo assíncrono muda o comportamento de toda a tela de upload. Migrar
o armazenamento de arquivos do volume local para o MinIO mexe com dado que já
existe. Nos dois casos, é preciso poder voltar atrás em segundos, sem esperar
uma reconstrução de imagem e um novo deploy.

Há ainda a dimensão experimental: o novo dashboard e o motor de alertas de
ritmo precisam ser comparados com o comportamento atual para que o artigo possa
afirmar algo sobre usabilidade com base em evidência.

## Decisão

Adotar **Unleash auto-hospedado**, dockerizado junto ao restante do ambiente,
com o SDK Python nos serviços e o SDK JavaScript no frontend.

**Quatro tipos de flag**, cada um com ciclo de vida próprio:

| Tipo | Para que serve | Vida útil |
| --- | --- | --- |
| `release` | Esconder trabalho em andamento até ficar pronto | Dias ou semanas — remover após liberação total |
| `experiment` | Comparar duas variantes com usuários | Duração do experimento |
| `ops` | Chave de desligamento de emergência | Permanente, revisada a cada semestre |
| `permission` | Habilitar recurso para um perfil específico | Permanente |

**Nomenclatura:** `<area>-<recurso>`, em kebab-case — `dashboard-v2`,
`ocr-assincrono`, `rag-busca-hibrida`.

**Inventário como código.** Toda flag é declarada em `docs/feature-flags.yaml`
com dono, tipo, data de criação, data limite de remoção e o que acontece quando
ela está desligada. O workflow `higiene-flags.yml` compara o inventário com o
código real e abre issue automaticamente para flags vencidas.

**Avaliação com valor padrão seguro.** Se o Unleash estiver indisponível, o SDK
devolve o padrão declarado no código, que é sempre o comportamento antigo e
conhecido. A indisponibilidade do serviço de flags nunca derruba a aplicação.

**Contexto de avaliação** enviado pelo SDK: e-mail do usuário, faixa de uso do
limite do MEI e ambiente. Isso permite liberação gradual por percentual e
segmentação por perfil — por exemplo, ativar os alertas de ritmo primeiro só
para quem já passou de 50% do limite, que é quem tem mais a ganhar com eles.

## Consequências

**A favor**

- Trabalho incompleto pode ser integrado na `main` sem risco, o que sustenta o
  trunk-based development do ADR-0002.
- Reversão passa a ser um clique, não um novo deploy — o que muda diretamente o
  tempo de restauração de serviço, uma das quatro métricas DORA medidas.
- Liberação percentual gradual transforma cada entrega arriscada em um
  experimento controlado, com métricas de negócio comparáveis entre variantes.
- A interface administrativa do Unleash rende evidência visual para a defesa.

**Contra**

- Cada flag ativa duplica um caminho de código e multiplica os estados a testar.
  É por isso que remoção com data marcada é obrigatória, e auditada pela CI.
- Mais dois contêineres: `unleash` e seu PostgreSQL.
- Testes precisam cobrir os dois lados de cada flag ativa. A suíte roda a matriz
  das flags marcadas como críticas.

## Alternativas descartadas

**Flagsmith.** Também open source e dockerizável, com interface mais simples e
configuração remota nativa. Descartado por ecossistema e documentação menores,
e por menor presença na literatura de entrega contínua.

**Serviço próprio de configuração.** Um `config-service` em FastAPI com uma
tabela de flags e cache em Redis resolveria o caso mais simples com muito menos
infraestrutura. Descartado porque liberação percentual estável, segmentação e
interface administrativa são justamente as partes difíceis — e reimplementá-las
seria escrever código que não é o objeto do trabalho.

**Variáveis de ambiente.** Mudar uma flag exigiria reiniciar o contêiner, o que
elimina o principal benefício: reversão imediata sem deploy.

## Referências

- Hodgson, P. *Feature Toggles (aka Feature Flags)*, martinfowler.com, 2017 —
  origem da taxonomia de quatro tipos adotada aqui.
- Humble, J.; Farley, D. *Continuous Delivery*, 2010, cap. 13.
- Documentação do Unleash sobre estratégias de ativação.
