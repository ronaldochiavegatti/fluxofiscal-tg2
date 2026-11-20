#!/usr/bin/env python3
"""Audita o inventário de feature flags contra o código real.

Uma feature flag sem data de remoção vira débito técnico permanente: o código
passa a ter dois caminhos vivos para sempre e a complexidade nunca volta ao
normal. Este script existe para que isso seja detectado por máquina, e não por
lembrança.

Dois modos:

  estrito   Falha quando o código usa uma flag que não está declarada em
            docs/feature-flags.yaml, ou quando uma declaração está malformada.
            Roda em todo Pull Request que toca serviços ou o inventário.

  vencidas  Lista as flags cuja data de remoção já passou. Com --abrir-issue,
            abre uma issue de débito técnico para cada uma, sem duplicar as
            que já têm issue aberta. Roda semanalmente.

Ver ADR-0008 e docs/feature-flags.yaml.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

# Chamadas que caracterizam uso de flag, no backend e no frontend.
# O primeiro argumento literal em string é o nome da flag.
PADROES_DE_USO = re.compile(
    r"""(?:esta_ativa|estaAtiva|is_enabled|isEnabled|useFlag|useFeatureFlag)"""
    r"""\s*\(\s*["']([a-z0-9][a-z0-9-]*)["']""",
)

EXTENSOES = {".py", ".ts", ".tsx", ".js", ".jsx"}
DIRETORIOS_IGNORADOS = {"node_modules", "__pycache__", ".venv", "dist", ".git"}

TIPOS_VALIDOS = {"release", "experiment", "ops", "permission"}
TIPOS_QUE_EXIGEM_REMOCAO = {"release", "experiment"}

CAMPOS_OBRIGATORIOS = ("nome", "tipo", "descricao", "quando_desligada", "servicos")


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------


def carregar_inventario(caminho: Path) -> list[dict]:
    if not caminho.exists():
        erro(f"inventário não encontrado: {caminho}")
    dados = yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}
    flags = dados.get("flags")
    if not isinstance(flags, list):
        erro(f"{caminho} não tem uma lista 'flags'")
    return flags


def varrer_codigo(raiz: Path) -> dict[str, list[str]]:
    """Devolve {nome_da_flag: [arquivo:linha, ...]} para todo uso encontrado."""
    usos: dict[str, list[str]] = {}
    if not raiz.exists():
        erro(f"diretório de código não encontrado: {raiz}")

    for arquivo in raiz.rglob("*"):
        if arquivo.suffix not in EXTENSOES:
            continue
        if DIRETORIOS_IGNORADOS & set(arquivo.parts):
            continue
        try:
            texto = arquivo.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for numero, linha in enumerate(texto.splitlines(), start=1):
            for nome in PADROES_DE_USO.findall(linha):
                usos.setdefault(nome, []).append(f"{arquivo}:{numero}")
    return usos


# ---------------------------------------------------------------------------
# Validação do inventário
# ---------------------------------------------------------------------------


def validar_declaracoes(flags: list[dict]) -> list[str]:
    problemas: list[str] = []
    vistos: set[str] = set()

    for indice, flag in enumerate(flags):
        if not isinstance(flag, dict):
            problemas.append(f"entrada {indice} não é um mapeamento")
            continue

        nome = flag.get("nome", f"<sem nome, entrada {indice}>")

        for campo in CAMPOS_OBRIGATORIOS:
            if not flag.get(campo):
                problemas.append(f"{nome}: campo obrigatório ausente ou vazio: {campo}")

        if nome in vistos:
            problemas.append(f"{nome}: declarada mais de uma vez")
        vistos.add(nome)

        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", str(nome)):
            problemas.append(f"{nome}: nome deve ser kebab-case minúsculo")

        tipo = flag.get("tipo")
        if tipo not in TIPOS_VALIDOS:
            problemas.append(f"{nome}: tipo inválido {tipo!r}; use um de {sorted(TIPOS_VALIDOS)}")

        remover_ate = flag.get("remover_ate")
        if tipo in TIPOS_QUE_EXIGEM_REMOCAO:
            if remover_ate is None:
                problemas.append(
                    f"{nome}: tipo {tipo} exige remover_ate. "
                    "Flag sem data de remoção é débito técnico permanente."
                )
            elif not isinstance(remover_ate, dt.date):
                problemas.append(f"{nome}: remover_ate deve ser uma data AAAA-MM-DD")
        elif remover_ate is not None:
            problemas.append(
                f"{nome}: tipo {tipo} é permanente e não deveria ter remover_ate; "
                "use revisar_em"
            )

        if "padrao_seguro" not in flag:
            problemas.append(
                f"{nome}: falta padrao_seguro. Toda flag precisa declarar o valor "
                "usado quando o serviço de flags está indisponível."
            )

    return problemas


# ---------------------------------------------------------------------------
# Modos
# ---------------------------------------------------------------------------


def modo_estrito(flags: list[dict], raiz_codigo: Path) -> int:
    declaradas = {f.get("nome") for f in flags if isinstance(f, dict)}
    usos = varrer_codigo(raiz_codigo)

    problemas = validar_declaracoes(flags)

    nao_declaradas = sorted(set(usos) - declaradas)
    for nome in nao_declaradas:
        locais = ", ".join(usos[nome][:3])
        problemas.append(
            f"{nome}: usada no código mas não declarada em docs/feature-flags.yaml "
            f"(ex.: {locais})"
        )

    if problemas:
        print("Auditoria de feature flags reprovada:\n")
        for p in problemas:
            print(f"  - {p}")
            print(f"::error::flag: {p}")
        print(f"\n{len(problemas)} problema(s).")
        return 1

    # Declarada e ainda não usada não é erro: neste projeto as flags são
    # declaradas junto com o planejamento, antes da implementação.
    nao_usadas = sorted(declaradas - set(usos))
    print(f"Auditoria aprovada: {len(declaradas)} flag(s) declarada(s), "
          f"{len(usos)} em uso no código.")
    if nao_usadas:
        print(f"\n{len(nao_usadas)} declarada(s) ainda sem uso (esperado antes da "
              f"implementação):")
        for nome in nao_usadas:
            print(f"  - {nome}")
    return 0


def flags_vencidas(flags: list[dict], hoje: dt.date) -> list[tuple[dict, int]]:
    vencidas = []
    for flag in flags:
        if not isinstance(flag, dict):
            continue
        prazo = flag.get("remover_ate")
        if isinstance(prazo, dt.date) and prazo < hoje:
            vencidas.append((flag, (hoje - prazo).days))
    return sorted(vencidas, key=lambda par: par[1], reverse=True)


def issue_ja_existe(repo: str, titulo: str) -> bool:
    try:
        saida = subprocess.run(
            ["gh", "issue", "list", "-R", repo, "--state", "open",
             "--search", titulo, "--json", "title", "--limit", "50"],
            capture_output=True, text=True, check=True,
        ).stdout
        return any(item.get("title") == titulo for item in json.loads(saida or "[]"))
    except (subprocess.CalledProcessError, json.JSONDecodeError, FileNotFoundError):
        # Na dúvida, não abre — duplicar issue é pior que não abrir.
        return True


def abrir_issue(repo: str, flag: dict, dias: int) -> None:
    nome = flag["nome"]
    titulo = f"chore: remover a feature flag vencida '{nome}'"

    if issue_ja_existe(repo, titulo):
        print(f"  issue já aberta para {nome}, nada a fazer")
        return

    corpo = f"""A flag `{nome}` passou da data de remoção há **{dias} dia(s)**.

| Campo | Valor |
| --- | --- |
| Tipo | `{flag.get('tipo')}` |
| Dono | {flag.get('dono', 'ronaldo')} |
| Remover até | {flag.get('remover_ate')} |
| Serviços | {', '.join(flag.get('servicos', []))} |

**O que ela faz:** {flag.get('descricao', '').strip()}

**Quando está desligada:** {flag.get('quando_desligada', '').strip()}

## Para fechar esta issue

1. Decidir qual caminho fica: o novo ou o antigo.
2. Remover do código o caminho descartado e a própria verificação da flag.
3. Arquivar a flag no Unleash.
4. Remover a entrada de `docs/feature-flags.yaml`.
5. Remover os testes do caminho que deixou de existir.

Enquanto a flag existir, o código mantém dois caminhos vivos e a
complexidade não volta ao normal. Ver [ADR-0008](docs/adr/0008-unleash-para-feature-flags.md).

_Issue aberta automaticamente por `tools/flags/auditar.py`._
"""

    try:
        subprocess.run(
            ["gh", "issue", "create", "-R", repo, "--title", titulo,
             "--body", corpo, "--label", "tipo:débito-técnico"],
            check=True,
        )
        print(f"  issue aberta para {nome}")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"::warning::não foi possível abrir issue para {nome}: {e}")


def modo_vencidas(flags: list[dict], repo: str | None, criar: bool) -> int:
    hoje = dt.date.today()
    vencidas = flags_vencidas(flags, hoje)

    if not vencidas:
        print(f"Nenhuma flag vencida em {hoje.isoformat()}.")
        return 0

    print(f"{len(vencidas)} flag(s) vencida(s) em {hoje.isoformat()}:\n")
    for flag, dias in vencidas:
        print(f"  - {flag['nome']}: vencida há {dias} dia(s) "
              f"(prazo era {flag['remover_ate']})")
        print(f"::warning::feature flag vencida: {flag['nome']} ({dias} dias)")

    if criar:
        if not repo:
            print("::error::--abrir-issue exige --repo")
            return 1
        print("\nAbrindo issues:")
        for flag, dias in vencidas:
            abrir_issue(repo, flag, dias)

    # Flag vencida não reprova o pipeline: ela gera issue e aviso. Reprovar
    # travaria entregas não relacionadas por causa de uma limpeza pendente.
    return 0


# ---------------------------------------------------------------------------


def erro(mensagem: str) -> None:
    print(f"::error::{mensagem}")
    sys.exit(2)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--inventario", type=Path, default=Path("docs/feature-flags.yaml"))
    p.add_argument("--codigo", type=Path, help="raiz do código a varrer (modo estrito)")
    p.add_argument("--modo", choices=["estrito", "vencidas"], default="estrito")
    p.add_argument("--abrir-issue", action="store_true")
    p.add_argument("--repo", help="owner/nome, para --abrir-issue")
    args = p.parse_args()

    flags = carregar_inventario(args.inventario)

    if args.modo == "estrito":
        if not args.codigo:
            erro("modo estrito exige --codigo")
        return modo_estrito(flags, args.codigo)

    return modo_vencidas(flags, args.repo, args.abrir_issue)


if __name__ == "__main__":
    sys.exit(main())
