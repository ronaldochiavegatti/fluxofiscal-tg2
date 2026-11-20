"""Trilha de auditoria — encadeamento por hash e imutabilidade (US-22)."""

import mongomock
import pytest

from app.auditoria import GENESE, RepositorioAuditoriaMongo, montar_registro


@pytest.fixture
def trilha() -> RepositorioAuditoriaMongo:
    return RepositorioAuditoriaMongo(mongomock.MongoClient()["fluxofiscal"]["auditoria"])


EXTRAIDO = {"metodo": "regex", "confianca": 0.9, "campos": {"value": 1200.0}}


def _extrair(trilha, recurso="doc1"):
    return trilha.registrar(
        por="marcia@mei.com.br",
        acao="documento.extraido",
        recurso_id=recurso,
        antes=None,
        depois=EXTRAIDO,
        trace_id="trace-1",
    )


def _confirmar(trilha, valor=1250.0, recurso="doc1"):
    return trilha.registrar(
        por="marcia@mei.com.br",
        acao="documento.confirmado",
        recurso_id=recurso,
        antes=EXTRAIDO,
        depois={"value": valor, "tx_type": "venda", "transacao_limits_id": 42},
        trace_id="trace-2",
    )


class TestEncadeamento:
    def test_primeiro_registro_aponta_para_a_genese(self, trilha):
        a = _extrair(trilha)
        assert a["seq"] == 1
        assert a["hash_anterior"] == GENESE

    def test_registro_seguinte_aponta_para_o_anterior(self, trilha):
        a = _extrair(trilha)
        b = _confirmar(trilha)
        assert b["seq"] == 2
        assert b["hash_anterior"] == a["hash"]

    def test_cadeia_integra_recem_escrita(self, trilha):
        _extrair(trilha)
        _confirmar(trilha)
        assert trilha.verificar_integridade() is True
        assert trilha.verificar_integridade("doc1") is True


class TestImutabilidade:
    def test_alterar_um_registro_quebra_a_cadeia(self, trilha):
        a = _extrair(trilha)
        _confirmar(trilha)

        # alteração direta no banco, fora do fluxo de escrita
        trilha._c.update_one({"_id": a["_id"]}, {"$set": {"depois.campos.value": 9999.0}})

        assert trilha.verificar_integridade() is False
        assert trilha.verificar_integridade("doc1") is False

    def test_remover_um_registro_do_meio_quebra_a_cadeia(self, trilha):
        _extrair(trilha)
        meio = _confirmar(trilha)
        _extrair(trilha, recurso="doc2")  # seq 3, encadeado em `meio`

        trilha._c.delete_one({"_id": meio["_id"]})

        # o seq 3 aponta para um hash_anterior que não existe mais
        assert trilha.verificar_integridade() is False

    def test_repositorio_nao_expoe_metodo_de_alteracao(self):
        publicos = {m for m in dir(RepositorioAuditoriaMongo) if not m.startswith("_")}
        assert publicos == {"registrar", "por_recurso", "listar", "verificar_integridade"}


class TestConsulta:
    def test_por_recurso_em_ordem_cronologica(self, trilha):
        _extrair(trilha)
        _confirmar(trilha)
        registros = trilha.por_recurso("doc1")
        assert [r["acao"] for r in registros] == ["documento.extraido", "documento.confirmado"]

    def test_a_trilha_conta_a_correcao(self, trilha):
        """Cenário Gherkin: extraído R$ 1.200 -> corrigido para R$ 1.250."""
        _extrair(trilha)
        _confirmar(trilha, valor=1250.0)

        confirmado = trilha.por_recurso("doc1")[1]
        assert confirmado["antes"]["campos"]["value"] == 1200.0
        assert confirmado["antes"]["metodo"] == "regex"
        assert confirmado["depois"]["value"] == 1250.0
        assert confirmado["em"]  # "quando"

    def test_listar_por_usuario_mais_recente_primeiro(self, trilha):
        _extrair(trilha)
        _confirmar(trilha)
        lista = trilha.listar("marcia@mei.com.br")
        assert [r["seq"] for r in lista] == [2, 1]
        assert trilha.listar("outro@mei.com.br") == []


def test_montar_registro_recusa_acao_desconhecida():
    with pytest.raises(ValueError, match="ação de auditoria"):
        montar_registro(
            seq=1,
            por="x",
            acao="documento.inventado",
            recurso_id="d",
            antes=None,
            depois={},
            trace_id=None,
            hash_anterior=GENESE,
        )
