---
description: Revisa o diff do branch atual contra a Definição de Concluído, via o agente revisor-pr
allowed-tools: Bash, Read, Grep, Glob, Task
---

Invoque o agente `revisor-pr` sobre o diff atual (`origin/main...HEAD`).

Passe ao agente:
- o nome do branch e a história US-XX que ele implementa;
- qualquer contexto de flag ou dependência relevante.

Quando o agente retornar, apresente os achados ao operador **sem corrigir
nada**. Só depois de os achados bloqueadores estarem resolvidos é que
`/abrir-pr` deve rodar.
