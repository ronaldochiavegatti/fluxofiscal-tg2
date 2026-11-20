#!/usr/bin/env python3
"""Verificador de compatibilidade de contrato entre serviços (US-47).

Compara o OpenAPI que um serviço publica hoje com o snapshot congelado em
``snapshots/<servico>.openapi.json`` e **reprova** quando a mudança quebra um
consumidor:

- rota removida;
- operação (método) removida numa rota;
- resposta ``2xx`` removida numa operação;
- campo que sumiu do schema de uma resposta ``2xx``.

Adicionar rota, operação ou campo é compatível e passa.

Uso na CI — o schema atual é extraído no ambiente do próprio serviço, onde
``from app import main`` funciona::

    PYTHONPATH=. python tools/contratos/extrair.py atual.json
    python tools/contratos/verificar.py --servico limits --atual atual.json

``--escrever`` (re)grava o snapshot e sai. Regravar é uma mudança explícita:
aparece no diff do PR e passa pela revisão junto com a quebra que a motivou.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
REPO = RAIZ.parent.parent
SNAPSHOTS = RAIZ / "snapshots"
MAPA_CONSUMIDORES = RAIZ / "consumidores.json"

METODOS = ("get", "put", "post", "delete", "patch", "options", "head")


def consumidores(servico: str) -> list[str]:
    """Quem depende das respostas deste serviço. Alimenta a mensagem de erro."""
    if not MAPA_CONSUMIDORES.exists():
        return []
    mapa = json.loads(MAPA_CONSUMIDORES.read_text("utf-8"))
    return list(mapa.get(servico, []))


def _resolver_ref(ref: str, raiz: dict) -> dict:
    no: object = raiz
    for parte in ref.lstrip("#/").split("/"):
        if not isinstance(no, dict):
            return {}
        no = no.get(parte, {})
    return no if isinstance(no, dict) else {}


def _propriedades(schema: dict, raiz: dict, vistos: frozenset[str] = frozenset()) -> set[str]:
    """Nomes de propriedade alcançáveis num schema de resposta.

    Resolve ``$ref``, combina ``allOf``/``anyOf``/``oneOf`` e desce em arrays.
    Campos aninhados aparecem com caminho pontilhado (``extracao.confianca``).
    A recursão para quando um ``$ref`` se repete, o que evita laço em schema
    recursivo.
    """
    if not isinstance(schema, dict):
        return set()

    if "$ref" in schema:
        ref = schema["$ref"]
        if ref in vistos:
            return set()
        return _propriedades(_resolver_ref(ref, raiz), raiz, vistos | {ref})

    nomes: set[str] = set()
    for chave in ("allOf", "anyOf", "oneOf"):
        for sub in schema.get(chave, []):
            nomes |= _propriedades(sub, raiz, vistos)
    if schema.get("type") == "array":
        nomes |= _propriedades(schema.get("items", {}), raiz, vistos)
    for nome, sub in schema.get("properties", {}).items():
        nomes.add(nome)
        nomes |= {f"{nome}.{aninhado}" for aninhado in _propriedades(sub, raiz, vistos)}
    return nomes


def _respostas_2xx(operacao: dict) -> dict:
    return {
        codigo: corpo
        for codigo, corpo in operacao.get("responses", {}).items()
        if codigo.startswith("2") or codigo == "default"
    }


def _schema_da_resposta(corpo: dict) -> dict:
    return corpo.get("content", {}).get("application/json", {}).get("schema", {})


def comparar(antigo: dict, novo: dict) -> list[str]:
    """Quebras de compatibilidade de ``antigo`` para ``novo``. Lista vazia = ok."""
    quebras: list[str] = []
    paths_antigos = antigo.get("paths", {})
    paths_novos = novo.get("paths", {})

    for rota, item_antigo in paths_antigos.items():
        item_novo = paths_novos.get(rota)
        if item_novo is None:
            quebras.append(f"rota removida: {rota}")
            continue

        for metodo in METODOS:
            op_antiga = item_antigo.get(metodo)
            if op_antiga is None:
                continue
            op_nova = item_novo.get(metodo)
            if op_nova is None:
                quebras.append(f"operação removida: {metodo.upper()} {rota}")
                continue

            resp_antigas = _respostas_2xx(op_antiga)
            resp_novas = _respostas_2xx(op_nova)
            for codigo, corpo_antigo in resp_antigas.items():
                corpo_novo = resp_novas.get(codigo)
                if corpo_novo is None:
                    quebras.append(f"resposta {codigo} removida: {metodo.upper()} {rota}")
                    continue
                props_antigas = _propriedades(_schema_da_resposta(corpo_antigo), antigo)
                props_novas = _propriedades(_schema_da_resposta(corpo_novo), novo)
                for sumido in sorted(props_antigas - props_novas):
                    quebras.append(
                        f"campo removido da resposta {codigo} de {metodo.upper()} {rota}: {sumido}"
                    )
    return quebras


def _gravar_snapshot(caminho: Path, schema: dict) -> None:
    SNAPSHOTS.mkdir(exist_ok=True)
    caminho.write_text(
        json.dumps(schema, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--servico", required=True, help="nome do diretório do serviço")
    parser.add_argument("--atual", required=True, type=Path, help="JSON do app.openapi() atual")
    parser.add_argument("--escrever", action="store_true", help="(re)grava o snapshot e sai")
    args = parser.parse_args(argv)

    atual = json.loads(args.atual.read_text("utf-8"))
    snapshot = SNAPSHOTS / f"{args.servico}.openapi.json"

    if args.escrever or not snapshot.exists():
        _gravar_snapshot(snapshot, atual)
        motivo = "regravado" if args.escrever else "criado (bootstrap)"
        try:
            rotulo = snapshot.relative_to(REPO)
        except ValueError:
            rotulo = snapshot
        print(f"::warning::snapshot de contrato {motivo}: {rotulo}")
        return 0

    quebras = comparar(json.loads(snapshot.read_text("utf-8")), atual)
    if not quebras:
        print(f"contrato de {args.servico}: compatível com o snapshot")
        return 0

    afetados = consumidores(args.servico) or ["(nenhum consumidor mapeado)"]
    print(
        f"::error::quebra de contrato em {args.servico} — "
        f"consumidores afetados: {', '.join(afetados)}"
    )
    for quebra in quebras:
        print(f"::error::  {quebra}")
    print()
    print("Se a quebra for intencional, alinhe com os consumidores e regrave o")
    print("snapshot no mesmo PR:")
    print(
        f"  PYTHONPATH=. python tools/contratos/extrair.py atual.json && "
        f"python tools/contratos/verificar.py --servico {args.servico} "
        f"--atual atual.json --escrever"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
