# ADR-0014 — Entrega contínua até o GHCR, deploy via Compose

- **Data:** 2026-08-22
- **Estado:** Aceita

## Contexto

Hoje não existe pipeline. A forma de executar o projeto é
`docker-compose up -d --build` na máquina do autor, o que significa que a imagem
que roda na apresentação é construída na hora, a partir do que estiver na pasta
naquele momento. Não há artefato imutável, não há garantia de que a
demonstração use o mesmo código que foi testado, e não há como voltar a uma
versão anterior que funcionava.

O artigo descreve o ambiente como "deploy em ambiente simulado de nuvem, usando
Docker Compose e MinIO", com migração futura para AWS Elastic Beanstalk. A
decisão de escopo desta fase manteve o Compose local como destino.

## Decisão

Levar a entrega contínua até o **registro de imagens**, e parar ali.

**O que o pipeline garante.** Todo commit na `main` que passa pela CI gera sete
imagens publicadas no **GitHub Container Registry**, marcadas com o SHA completo
do commit, com a versão semântica quando houver tag, e com `latest`. Cada imagem
carrega SBOM e proveniência SLSA anexados pelo buildkit, e é escaneada pelo
Trivy depois de publicada.

> **Limitação medida em execução.** O armazenamento de atestados do GitHub —
> o passo `actions/attest-build-provenance` — não está disponível em
> repositório privado de conta pessoal. A primeira execução da CD reprovou por
> isso, **depois** de já ter publicado as imagens. O passo passou a ser
> condicionado à visibilidade do repositório. A proveniência e o SBOM anexados
> à própria imagem continuam existindo: o que se perde é a verificação via
> `gh attestation verify`, que exige o repositório público.

**O que o deploy é.** Um `docker-compose.release.yml` que consome as imagens do
GHCR em vez de construir localmente. A demonstração passa a ser
`docker compose -f docker-compose.release.yml pull && up -d`: mesma imagem que
passou na CI, sem reconstrução, sem surpresa no dia da apresentação.

**Rastreabilidade.** Cada execução registra um deployment na API do GitHub, o
que alimenta as métricas de frequência de implantação e lead time do workflow
`dora.yml` (ADR-0007).

**Reversão.** Trocar a tag de imagem no arquivo de release e subir de novo.
Para mudança de comportamento protegida por flag, a reversão é ainda mais
rápida: desligar a flag no Unleash (ADR-0008).

**Ambientes.** Dois perfis do Compose no mesmo arquivo:

| Perfil | Uso | Origem das imagens |
| --- | --- | --- |
| `dev` | Desenvolvimento com recarga automática | construídas localmente |
| `release` | Demonstração e avaliação | GHCR, marcadas por SHA |

O perfil `observability` sobe a pilha Grafana e é opcional em ambos.

## Consequências

**A favor**

- A imagem demonstrada é exatamente a imagem testada.
- Reversão passa a existir, o que é pré-requisito para medir tempo de
  restauração de serviço.
- SBOM e proveniência anexados à imagem dão à cadeia de suprimentos um
  tratamento que raramente aparece em trabalho de graduação, e rendem argumento
  na defesa — com a ressalva de verificação registrada acima.
- Zero custo: GHCR é gratuito para repositório privado dentro da cota da conta.

**Contra**

- Não há ambiente público para a banca acessar por conta própria. Aceito: a
  avaliação acontece com a aplicação rodando na máquina do autor.
- Nenhuma afirmação sobre comportamento em nuvem real pode ser feita a partir de
  evidência — só a partir de arquitetura.
- Puxar sete imagens exige rede na hora da demonstração. Mitigado por um
  `docker compose pull` na véspera, já que as imagens ficam em cache local.

## Alternativas descartadas

**Deploy real em nuvem.** Daria uma URL viva para a banca e permitiria falar de
comportamento em produção com dados. Descartado nesta fase por decisão de
escopo: envolveria custo recorrente, gestão de segredos em ambiente público e a
resolução prévia do ADR-0011, já que a plataforma ainda não tem autenticação.

**Kubernetes local com kind ou k3s.** Permitiria demonstrar escalabilidade
horizontal com autoescalamento e números reais — o argumento mais forte possível
para a seção de escalabilidade. Descartado pela complexidade desproporcional ao
restante do escopo. Fica registrado como a evolução natural desta decisão.

**Continuar só com build local.** Mantém o problema de origem: nada garante que
o que roda é o que foi testado.

## Referências

- Humble, J.; Farley, D. *Continuous Delivery*, 2010, cap. 5 (o princípio de
  construir o binário uma única vez).
- Documentação do GitHub sobre atestados de proveniência de build.
- Especificação SLSA, nível 2.
