# ADR-0022 — Regras fiscais parametrizáveis por usuário

- **Data:** 2026-11-15
- **Estado:** Aceita
- **Issue:** #91

## Contexto

Os números do painel dependiam de constantes fixas em
`app/services/limits/app/dominio/`: teto anual (R$ 81.000,00), faixa de alerta
(80%), margem de desenquadramento (20%), meta mensal (teto ÷ 12), alerta de
concentração de cliente (70%) e os limiares da projeção de ritmo (30 dias,
3 vendas, 60 dias de abertura recente, 60% para venda atípica, 50% para
atenção por ritmo).

O usuário precisa ajustar esses valores quando o regulamento do MEI mudar (o
teto não muda desde 2018, mas há projetos de lei para corrigi-lo) e para
refletir metas pessoais. Ao mesmo tempo, o CLAUDE.md proíbe regra fiscal fora
de `dominio/` — configurar no frontend e calcular lá duplicaria a regra.

## Decisão

1. **O domínio recebe os números como parâmetro.** `dominio/parametros.py`
   define `ParametrosFiscais` (imutável, validado na construção) com os
   valores oficiais vigentes como padrão. As funções de `limites.py`,
   `ritmo.py` e `faturamento.py` recebem os parâmetros; sem eles, usam o
   padrão — o comportamento de antes, sem mudança para quem não configura.
   `parametros.py` é a folha do pacote: os demais módulos importam dele, e as
   constantes antigas continuam reexportadas onde sempre estiveram.

2. **A configuração mora no `limits`, por usuário.** Tabela
   `configuracao_fiscal` (no banco do próprio serviço — não é dependência
   estrutural nova) com só os campos que o usuário mudou, em JSON, e a data de
   abertura do MEI. Rotas `GET/PUT/DELETE /configuracao/{email}`. A validação
   é a do domínio: o que `ParametrosFiscais` recusa vira 422 com a mensagem
   dele.

3. **Tudo é configurável**, inclusive os limiares técnicos da projeção
   (decisão do usuário na #91).

4. **A configuração do usuário é a fonte.** Os padrões servem só de ponto de
   partida para quem nunca configurou; o sistema não os atualiza sozinho
   quando a lei muda. Quem quiser o novo valor oficial altera na tela.

5. **Atrás da flag `metricas-configuraveis`** (padrão seguro: desligada).
   Desligada, as rotas do painel usam o padrão e ignoram a configuração
   gravada.

6. **O frontend só edita e exibe.** A tela de Configurações converte unidades
   (0,80 ↔ 80%) e mostra o erro devolvido pelo domínio no campo citado; não
   valida faixas nem recalcula nada.

## Consequências

- Todas as rotas que usam regra fiscal (`/summary`, `/ritmo`, `/mensal`,
  `/concentracao` e o relatório em PDF) leem a configuração do usuário. O
  agente recebe o limiar de alerta configurado pelo resumo
  (`alert_threshold_percent`) e o cita no prompt em vez de "80%" fixo.
- Configuração gravada que ficou inválida (um campo removido do domínio, por
  exemplo) não derruba o painel: cai no padrão e registra um aviso no log.
- Guardar só os ajustes faz um parâmetro novo no domínio chegar a todos com o
  próprio padrão, sem migração.
- Risco aceito: o usuário pode informar um teto errado e receber orientação
  errada. A tela mostra o valor padrão ao lado de cada campo e um "voltar ao
  padrão", e o painel marca o que está personalizado.
