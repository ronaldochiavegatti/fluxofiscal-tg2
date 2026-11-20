# ADR-0009 — Serviço de Insights com modelo de leitura (CQRS)

- **Data:** 2026-08-22
- **Estado:** Aceita

## Contexto

O pedido central desta fase é um dashboard mais rico: métricas visuais, alertas
de ritmo de vendas e gráficos de acompanhamento do limite anual. Nada disso é
uma consulta simples.

Uma projeção de estouro do limite depende do faturamento acumulado no ano, da
média móvel dos últimos 30 e 90 dias, do número de dias decorridos, do mês de
abertura do MEI (que muda o limite quando a abertura foi no meio do ano) e da
comparação com o mesmo período do ano anterior. Calcular isso a cada
carregamento de tela, sobre a tabela transacional, significa varreduras
repetidas e latência crescendo com o histórico do usuário.

O Limits Service hoje faz uma coisa e faz bem: registra transações e devolve o
resumo anual. O `GET /summary/{email}` já é a função mais chamada da plataforma
— o dashboard, o agente de IA e o relatório em PDF dependem dela. Empilhar ali
o motor analítico misturaria dois modelos com requisitos opostos: escrita
transacional e consistente de um lado, leitura agregada e tolerante a atraso do
outro.

## Decisão

Criar o **Insights Service**, um modelo de leitura separado no espírito do CQRS,
alimentado pelos eventos do ADR-0006.

**Responsabilidades**

1. Consumir `transacao.criada`, `transacao.atualizada`, `transacao.removida` e
   `documento.confirmado`.
2. Manter projeções materializadas por usuário e ano: totais mensais e diários,
   médias móveis, ticket médio, concentração por cliente, série do acumulado.
3. Calcular os indicadores de ritmo: taxa diária, índice de ritmo, projeção
   anual, data prevista de estouro, faturamento seguro por mês restante.
4. Avaliar as regras de alerta e publicar `alerta.disparado`.
5. Servir o dashboard e o motor de contexto do agente com uma resposta única e
   pronta.

**Fronteira explícita.** O Insights **nunca escreve** dado transacional. A fonte
da verdade continua sendo o Limits; o Insights é derivado e pode ser
reconstruído do zero reprocessando os eventos.

**Reconstrução da projeção.** Um comando administrativo recalcula tudo a partir
do Limits. Isso é o que torna seguro corrigir um erro de fórmula: em vez de
migração de dados, basta corrigir o código e reprocessar.

**Consistência.** Eventual, com atraso alvo abaixo de 2 segundos entre a
transação e a projeção atualizada. O dashboard exibe o horário do último
recálculo, e a página oferece atualização manual. Onde o número precisa estar
exato na hora — o total do resumo anual — a interface continua lendo o Limits
diretamente.

## Consequências

**A favor**

- O dashboard responde em uma chamada, com dados pré-agregados, em vez de várias
  consultas e cálculo no navegador.
- O motor de alertas ganha um lugar natural, em vez de virar `useMemo` espalhado
  pelos componentes React — que é onde a lógica de percentual mora hoje.
- A lógica analítica passa a ser testável de forma isolada, com eventos
  sintéticos, sem subir banco transacional.
- O agente de IA passa a receber um retrato fiscal rico em vez do resumo raso de
  hoje, o que melhora diretamente a qualidade das respostas.

**Contra**

- Mais um serviço e mais um banco para operar.
- Duplicação de dado por definição, com o risco de divergência entre a projeção
  e a fonte. Mitigado por uma verificação de conciliação noturna que compara os
  totais e alerta em caso de diferença.
- O usuário pode ver por instantes um dashboard levemente atrasado em relação à
  tabela de transações.

## Alternativas descartadas

**Calcular tudo no frontend.** É o que acontece hoje com o percentual do limite.
Não escala para médias móveis e projeções, obriga a baixar o histórico inteiro
para o navegador e espalha regra de negócio fiscal pela camada de apresentação.

**Estender o Limits Service.** Menos infraestrutura, e seria a escolha certa se
o motor analítico fosse pequeno. Descartada porque colocaria um caminho de
leitura pesado dentro do serviço mais crítico da plataforma, e porque o Limits
tem uma responsabilidade clara que vale a pena preservar.

**Views materializadas no PostgreSQL do Limits.** Solução elegante e barata para
agregação. Descartada porque o motor de alertas precisa de lógica condicional
com estado — reconhecer que um alerta já foi disparado, respeitar período de
silêncio, escalonar nível — e isso não cabe bem em SQL.

## Referências

- Fowler, M. *CQRS*, martinfowler.com, 2011.
- Richardson, C. *Microservices Patterns*, 2018, cap. 7 (consultas em
  arquiteturas de microsserviços).
