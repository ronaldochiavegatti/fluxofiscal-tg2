# ADR-0011 — Manter autenticação simplificada nesta fase

- **Data:** 2026-08-22
- **Estado:** Aceita
- **Revisão obrigatória:** antes de qualquer exposição pública da plataforma

## Contexto

A autenticação atual é deliberadamente rasa. O `POST /auth/login` verifica a
senha com bcrypt e devolve `{"message": "login ok", "user_id": 1}` — sem token,
sem sessão, sem expiração. O comentário no código diz o que falta: "Depois aqui
vai entrar geração de JWT". O frontend guarda o usuário de demonstração no
`localStorage` e passa o e-mail como parâmetro em cada chamada.

A consequência é que **todo endpoint da plataforma é público e a identidade é
autodeclarada**. Qualquer requisição com `email=outro@mei.com` lê as transações,
o saldo de tokens e os documentos indexados de outra pessoa. O `DELETE
/limits/reset/{email}` apaga o histórico de quem for informado ali.

O artigo já registra isso como limitação conhecida, na conclusão e na seção de
integração frontend-backend.

## Decisão

**Manter a autenticação simplificada nesta fase**, e tratar essa escolha como
uma restrição explícita de escopo, não como um esquecimento.

Em contrapartida, três medidas passam a ser obrigatórias:

**1. A limitação fica documentada onde ela existe.** Um aviso no `README`, um
banner permanente na interface identificando o modo demonstração, e um campo
`"modo": "demonstracao"` na resposta de todos os endpoints de saúde. Ninguém
deve descobrir por acidente que os dados não são protegidos.

**2. O caminho de saída fica preparado.** Toda rota nova nasce recebendo a
identidade do usuário por uma dependência do FastAPI —
`usuario_atual: Usuario = Depends(obter_usuario_atual)` — mesmo que a
implementação atual apenas leia o e-mail do parâmetro. Trocar essa função por
validação de JWT depois é uma mudança em um arquivo, não em trinta rotas. Sem
essa disciplina, o custo de introduzir autenticação real cresce a cada endpoint
criado.

**3. Nada de dado pessoal real.** O ambiente roda exclusivamente com dados
sintéticos. Os documentos de teste em `docs_para_teste/` são fictícios e devem
continuar assim. A plataforma não sobe em endereço público enquanto este ADR
estiver em vigor.

**Critério de reversão.** Este ADR deve ser substituído antes de: expor a
aplicação em URL pública, aceitar upload de nota fiscal real de terceiro, ou
cadastrar mais de um usuário real. O trabalho correspondente já está no backlog
como épico EP11, estimado em 21 pontos.

## Consequências

**A favor**

- O esforço desta fase vai inteiro para o que o trabalho se propôs a demonstrar:
  dashboard, observabilidade, entrega contínua, arquitetura assíncrona e
  engenharia de contexto.
- Testes e demonstrações ficam mais simples, sem gestão de sessão.
- A decisão fica registrada com data, motivo e critério de revisão — que é
  diferente de simplesmente não ter feito.

**Contra**

- A plataforma continua sem poder ser exposta publicamente. É a consequência
  central e ela é aceita conscientemente.
- Nenhuma métrica de segurança de acesso pode ser reivindicada no artigo.
- O trabalho de autenticação se acumula: cada endpoint criado agora é um
  endpoint a proteger depois. Mitigado pela medida 2.

## Alternativas descartadas

**JWT com refresh e RBAC agora.** Resolveria a maior limitação registrada na
conclusão do artigo e habilitaria multiusuário real. Descartado nesta rodada por
decisão de escopo: consumiria uma onda inteira que foi priorizada para as
frentes que o trabalho quer demonstrar.

**JWT simples, sem refresh.** Meio-termo de menor custo. Descartado pelo mesmo
motivo, com o agravante de entregar uma segurança parcial que poderia ser
confundida com segurança real.

## Referências

- OWASP API Security Top 10, categoria API1:2023 (Broken Object Level
  Authorization) — descreve exatamente a exposição atual.
- Seção "Conclusões" do artigo, que já registra a limitação.
