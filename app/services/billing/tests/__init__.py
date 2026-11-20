"""Pacote de testes do Billing.

Existe para que `tests` seja importável como pacote: sem ele, o pytest carrega
`conftest.py` como módulo de topo e um `from tests.conftest import ...` criaria
uma segunda cópia do mesmo módulo.
"""
