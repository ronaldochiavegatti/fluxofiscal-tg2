#!/usr/bin/env python3
"""Extrai o OpenAPI do serviço FastAPI do diretório de trabalho atual (US-47).

Roda de dentro de ``app/services/<servico>/``, com ``PYTHONPATH=.`` para que
``from app import main`` resolva. Não sobe o serviço nem abre conexão — só chama
``app.openapi()``.

    PYTHONPATH=. python ../../../tools/contratos/extrair.py atual.json
"""

from __future__ import annotations

import json
import sys

from app import main  # type: ignore[import-not-found]


def principal(destino: str | None) -> None:
    schema = main.app.openapi()
    texto = json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True)
    if destino:
        with open(destino, "w", encoding="utf-8") as arquivo:
            arquivo.write(texto + "\n")
    else:
        sys.stdout.write(texto)


if __name__ == "__main__":
    principal(sys.argv[1] if len(sys.argv) > 1 else None)
