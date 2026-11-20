"""Testes do Agent Orchestrator.

O que este serviço monta é um prompt, e o prompt é onde mora a regra fiscal
repetida pela terceira vez. Os testes cobram o que o artigo afirma sobre ela:
que despesa nunca é somada ao faturamento, e que o alerta de proximidade do
teto aparece mesmo quando o usuário perguntou outra coisa.

Nenhum teste chama a API do Gemini. Sem `GEMINI_API_KEY` o serviço entra em
modo de demonstração — e o modo de demonstração precisa continuar respondendo,
porque é ele que roda quando a cota acaba.
"""

import pytest

from app import main
from tests.conftest import EMAIL, OUTRO, RESUMO, RespostaFalsa


class _ModelosFalsos:
    def __init__(self, texto=None, erro=None, embedding=None):
        self._texto = texto
        self._erro = erro
        self._embedding = embedding
        self.prompts = []

    def generate_content(self, **kwargs):
        self.prompts.append(kwargs.get("contents"))
        if self._erro is not None:
            raise self._erro
        return type("Resposta", (), {"text": self._texto})()

    def embed_content(self, **kwargs):
        if self._erro is not None:
            raise self._erro
        valores = type("Valores", (), {"values": self._embedding})()
        return type("Resultado", (), {"embeddings": [valores]})()


class _ClienteFalso:
    def __init__(self, texto=None, erro=None, embedding=None):
        self.models = _ModelosFalsos(texto, erro, embedding)


class TestHealth:
    def test_declara_que_o_rag_esta_desligado_sem_chave(self, cliente):
        corpo = cliente.get("/health").json()

        assert corpo["status"] == "ok"
        assert corpo["service"] == "agent-orchestrator"
        assert corpo["rag_enabled"] is False


class TestSegmentacao:
    def test_texto_curto_vira_um_trecho(self):
        assert main.chunk_text("uma nota curta") == ["uma nota curta"]

    def test_texto_longo_e_dividido(self):
        trechos = main.chunk_text("x" * 2000, max_chars=900)

        assert [len(t) for t in trechos] == [900, 900, 200]

    @pytest.mark.parametrize("entrada", ["", "   ", "\n\n"])
    def test_texto_vazio_nao_gera_trecho(self, entrada):
        assert main.chunk_text(entrada) == []


class TestEmbeddings:
    def test_sem_chave_nao_ha_embedding(self):
        """Modo de demonstração: o serviço responde, mas sem recuperação."""
        assert main.gemini_client is None
        assert main.embed_text("qualquer coisa") is None

    def test_com_cliente_devolve_o_vetor(self, monkeypatch):
        monkeypatch.setattr(main, "gemini_client", _ClienteFalso(embedding=[0.1, 0.2, 0.3]))

        assert main.embed_text("pergunta") == [0.1, 0.2, 0.3]

    def test_texto_vazio_nao_gasta_chamada(self, monkeypatch):
        monkeypatch.setattr(main, "gemini_client", _ClienteFalso(embedding=[0.1]))

        assert main.embed_text("   ") is None

    def test_falha_na_chamada_devolve_nulo(self, monkeypatch):
        monkeypatch.setattr(main, "gemini_client", _ClienteFalso(erro=RuntimeError("cota")))

        assert main.embed_text("pergunta") is None


class TestRecuperacao:
    def test_sem_embedding_nao_ha_o_que_recuperar(self, cliente):
        """Sem vetor da pergunta, a busca por similaridade não faz sentido."""
        db = main.SessionLocal()
        try:
            assert main.retrieve_knowledge(db, []) == []
            assert main.retrieve_document_chunks(db, EMAIL, []) == []
        finally:
            db.close()


class TestBaseDeConhecimento:
    def test_seed_carrega_na_inicializacao(self, cliente):
        db = main.SessionLocal()
        try:
            assert db.query(main.KnowledgeChunk).count() == len(main.MEI_KNOWLEDGE_SEED)
        finally:
            db.close()

    def test_seed_e_idempotente(self, cliente):
        """Deploy novo não pode duplicar o que já está na base."""
        main.seed_knowledge_base()
        main.seed_knowledge_base()

        db = main.SessionLocal()
        try:
            assert db.query(main.KnowledgeChunk).count() == len(main.MEI_KNOWLEDGE_SEED)
        finally:
            db.close()

    def test_seed_vetoriza_trechos_gravados_sem_embedding(self, cliente, monkeypatch):
        """Base criada sem chave do Gemini é vetorizada quando a chave chega.

        Sem isso, a busca (que ignora `embedding` nulo) nunca enxergaria a base
        de quem subiu a pilha a primeira vez sem `GEMINI_API_KEY`.
        """
        db = main.SessionLocal()
        try:
            assert all(c.embedding is None for c in db.query(main.KnowledgeChunk).all())
        finally:
            db.close()

        vetor = [0.1] * main.EMBEDDING_DIM
        monkeypatch.setattr(main, "embed_text", lambda _texto, **_: vetor)
        main.seed_knowledge_base()

        db = main.SessionLocal()
        try:
            trechos = db.query(main.KnowledgeChunk).all()
            assert len(trechos) == len(main.MEI_KNOWLEDGE_SEED)
            assert all(c.embedding is not None for c in trechos)
        finally:
            db.close()

    def test_seed_atualiza_e_revetoriza_trecho_corrigido_no_codigo(self, cliente, monkeypatch):
        """Correção de texto no código chega à base já populada (caso do R2).

        O seed é idempotente por título; sem comparar o conteúdo, a versão
        antiga e errada continuaria sendo servida ao RAG para sempre.
        """
        titulo = "Consequências de ultrapassar o limite anual"
        db = main.SessionLocal()
        try:
            trecho = db.query(main.KnowledgeChunk).filter_by(title=titulo).one()
            trecho.content = "retroativo ao mês em que o limite foi excedido"
            db.commit()
        finally:
            db.close()

        vetor = [0.2] * main.EMBEDDING_DIM
        monkeypatch.setattr(main, "embed_text", lambda _texto, **_: vetor)
        main.seed_knowledge_base()

        db = main.SessionLocal()
        try:
            trecho = db.query(main.KnowledgeChunk).filter_by(title=titulo).one()
            assert "1º de janeiro" in trecho.content
            assert trecho.embedding is not None
            assert db.query(main.KnowledgeChunk).count() == len(main.MEI_KNOWLEDGE_SEED)
        finally:
            db.close()

    def test_r2_retroage_a_primeiro_de_janeiro(self):
        """LC 123/2006 art. 18-A; Res. CGSN 140/2018 art. 115."""
        r2 = next(c for _s, t, c in main.MEI_KNOWLEDGE_SEED if t.startswith("Consequências"))
        assert "1º de janeiro do ano em que o limite foi excedido" in r2
        assert "ao mês em que" not in r2

    def test_a_regra_de_que_so_venda_conta_esta_na_base(self, cliente):
        """A mesma regra do núcleo fiscal, na forma que o agente cita."""
        db = main.SessionLocal()
        try:
            titulos = [t for (t,) in db.query(main.KnowledgeChunk.title).all()]
        finally:
            db.close()

        assert any("vendas contam" in titulo for titulo in titulos)


class TestConsultaAoLimits:
    def test_devolve_o_resumo(self, limits_falso):
        assert main.get_limits_summary(EMAIL) == RESUMO
        assert limits_falso == [f"{main.LIMITS_BASE_URL}/summary/{EMAIL}"]

    def test_limits_fora_do_ar_vira_502(self, monkeypatch):
        def _get(url, timeout=5.0):
            raise main.httpx.ConnectError("recusou a conexao")

        monkeypatch.setattr(main.httpx, "get", _get)

        with pytest.raises(main.HTTPException) as erro:
            main.get_limits_summary(EMAIL)

        assert erro.value.status_code == 502

    def test_erro_do_limits_e_repassado(self, monkeypatch):
        monkeypatch.setattr(
            main.httpx, "get", lambda url, timeout=5.0: RespostaFalsa(404, texto="sem usuario")
        )

        with pytest.raises(main.HTTPException) as erro:
            main.get_limits_summary(EMAIL)

        assert erro.value.status_code == 404


class TestMontagemDoPrompt:
    def _montar(self, **ajustes):
        return main.build_prompt(
            retrato=main.traduzir_resumo_limits({**RESUMO, **ajustes}),
            user_message="quanto ainda posso faturar?",
            email=EMAIL,
            knowledge_hits=[],
            document_hits=[],
        )

    def test_carrega_os_numeros_do_resumo(self):
        prompt = self._montar()

        assert "R$ 47.304,00" in prompt
        assert "R$ 81.000,00" in prompt
        assert "R$ 33.696,00" in prompt

    def test_separa_faturamento_de_despesa(self):
        """A instrução existe porque somar os dois é o erro que mais custa caro.

        Um agente que soma despesa ao faturamento diz a um MEI que ele estourou
        o limite quando não estourou.
        """
        prompt = self._montar()

        assert "SOMA APENAS DAS VENDAS" in prompt
        assert "NUNCA some despesas" in prompt

    def test_faixa_de_alerta_gera_aviso_proativo(self):
        prompt = self._montar(alert_level="warning", percent_used=85.0)

        assert "85.0%" in prompt
        assert "mesmo que a pergunta dele seja sobre outro assunto" in prompt

    def test_limite_ultrapassado_abre_a_resposta(self):
        prompt = self._montar(alert_level="exceeded", exceeded=True)

        assert "JÁ ULTRAPASSOU" in prompt
        assert "antes de qualquer outra orientação" in prompt

    def test_pede_abstencao_quando_a_base_nao_basta(self):
        """Sem esta instrução o modelo completava com conhecimento geral.

        No teste de abstenção de 19/11/2026, perguntado sobre auxílio-doença
        (fora da base), o assistente respondeu com carência e perícia sem dizer
        que nada daquilo vinha da base de regras.
        """
        prompt = self._montar()

        assert "a base de regras" in prompt
        assert "consultada não traz essa informação" in prompt
        assert "Não complete a resposta com conhecimento geral" in prompt
        assert "qual parte" in prompt

    def test_sem_alerta_nao_ha_instrucao_extra(self):
        prompt = self._montar()

        assert "ATENÇÃO" not in prompt

    def test_contexto_recuperado_entra_com_a_fonte(self):
        prompt = main.build_prompt(
            retrato=main.traduzir_resumo_limits(RESUMO),
            user_message="posso ultrapassar?",
            email=EMAIL,
            knowledge_hits=[
                main.KnowledgeChunk(source="Receita Federal", title="Limite", content="R$ 81 mil")
            ],
            document_hits=[main.DocumentChunk(source_filename="nota.pdf", content="Servico")],
        )

        assert "(Receita Federal) Limite: R$ 81 mil" in prompt
        assert "(arquivo: nota.pdf) Servico" in prompt


class TestChamadaAoModelo:
    def test_modo_demonstracao_avisa_que_esta_sem_chave(self):
        resposta = main.call_gemini("prompt qualquer")

        assert "modo demonstração" in resposta
        assert "GEMINI_API_KEY" in resposta

    def test_resposta_do_modelo_e_devolvida(self, monkeypatch):
        monkeypatch.setattr(main, "gemini_client", _ClienteFalso(texto="Você pode faturar mais."))

        assert main.call_gemini("prompt") == "Você pode faturar mais."

    def test_resposta_vazia_nao_vira_string_vazia(self, monkeypatch):
        monkeypatch.setattr(main, "gemini_client", _ClienteFalso(texto=""))

        assert "Não consegui gerar" in main.call_gemini("prompt")

    def test_falha_do_modelo_vira_mensagem_e_nao_excecao(self, monkeypatch):
        """O chat precisa responder algo. Erro 500 na cara do usuário, não."""
        monkeypatch.setattr(main, "gemini_client", _ClienteFalso(erro=RuntimeError("cota")))

        resposta = main.call_gemini("prompt")

        assert "erro ao chamar o modelo" in resposta
        assert "RuntimeError" in resposta


class TestChat:
    def test_responde_em_modo_demonstracao(self, cliente, limits_falso):
        resposta = cliente.post("/chat", json={"email": EMAIL, "message": "quanto falta?"})

        assert resposta.status_code == 200
        corpo = resposta.json()
        assert "modo demonstração" in corpo["reply"]
        assert corpo["sources"] == []

    def test_consulta_o_limits_do_usuario_certo(self, cliente, limits_falso):
        cliente.post("/chat", json={"email": OUTRO, "message": "oi"})

        assert limits_falso == [f"{main.LIMITS_BASE_URL}/summary/{OUTRO}"]

    def test_cita_as_fontes_recuperadas(self, cliente, limits_falso, monkeypatch):
        monkeypatch.setattr(main, "embed_text", lambda _, **__: [0.1])
        monkeypatch.setattr(
            main,
            "retrieve_knowledge",
            lambda db, emb, top_k=3: [
                main.KnowledgeChunk(source="Receita Federal", title="Limite", content="R$ 81 mil")
            ],
        )
        monkeypatch.setattr(
            main,
            "retrieve_document_chunks",
            lambda db, email, emb, top_k=3: [
                main.DocumentChunk(source_filename="nota.pdf", content="Servico")
            ],
        )

        corpo = cliente.post("/chat", json={"email": EMAIL, "message": "posso?"}).json()

        assert corpo["sources"] == ["Limite (Receita Federal)", "Documento: nota.pdf"]

    def test_limits_fora_do_ar_nao_vira_500(self, cliente, monkeypatch):
        def _get(url, timeout=5.0):
            raise main.httpx.ConnectError("recusou a conexao")

        monkeypatch.setattr(main.httpx, "get", _get)

        resposta = cliente.post("/chat", json={"email": EMAIL, "message": "oi"})

        assert resposta.status_code == 502

    def test_email_invalido_e_recusado_pelo_contrato(self, cliente):
        resposta = cliente.post("/chat", json={"email": "nao-e-email", "message": "oi"})

        assert resposta.status_code == 422


class TestIndexacao:
    def test_guarda_o_texto_do_documento(self, cliente):
        resposta = cliente.post(
            "/index-document",
            json={"email": EMAIL, "source_filename": "nota.pdf", "content": "Servico de manicure"},
        )

        assert resposta.status_code == 200
        db = main.SessionLocal()
        try:
            trechos = db.query(main.DocumentChunk).filter_by(user_email=EMAIL).all()
        finally:
            db.close()
        assert [t.content for t in trechos] == ["Servico de manicure"]

    def test_sem_embedding_o_trecho_e_guardado_mas_nao_conta(self, cliente):
        """`chunks_indexed` conta o que ficou recuperável, não o que foi gravado.

        Em modo de demonstração o texto é preservado para quando houver chave,
        mas ainda não participa da busca por similaridade.
        """
        corpo = cliente.post(
            "/index-document", json={"email": EMAIL, "content": "Servico de manicure"}
        ).json()

        assert corpo["chunks_indexed"] == 0

    def test_conteudo_vazio_nao_grava_nada(self, cliente):
        corpo = cliente.post("/index-document", json={"email": EMAIL, "content": "   "}).json()

        assert corpo["chunks_indexed"] == 0
        db = main.SessionLocal()
        try:
            assert db.query(main.DocumentChunk).count() == 0
        finally:
            db.close()

    def test_texto_longo_vira_varios_trechos(self, cliente, monkeypatch):
        # A coluna `Vector` recusa vetor com dimensão diferente da declarada,
        # então o duplo precisa ter o tamanho real do modelo de embeddings.
        monkeypatch.setattr(main, "embed_text", lambda _, **__: [0.0] * main.EMBEDDING_DIM)

        corpo = cliente.post("/index-document", json={"email": EMAIL, "content": "x" * 2000}).json()

        assert corpo["chunks_indexed"] == 3


class TestReset:
    def test_apaga_os_documentos_do_usuario(self, cliente):
        cliente.post("/index-document", json={"email": EMAIL, "content": "documento da Marcia"})
        cliente.post("/index-document", json={"email": OUTRO, "content": "documento do Douglas"})

        resposta = cliente.delete(f"/reset/{EMAIL}")

        assert resposta.json() == {"email": EMAIL, "document_chunks_deleted": 1}

    def test_preserva_a_base_de_conhecimento(self, cliente):
        """As regras do MEI não são dado do usuário: reset não as apaga."""
        cliente.delete(f"/reset/{EMAIL}")

        db = main.SessionLocal()
        try:
            assert db.query(main.KnowledgeChunk).count() == len(main.MEI_KNOWLEDGE_SEED)
        finally:
            db.close()

    def test_nao_toca_nos_documentos_de_outro_usuario(self, cliente):
        cliente.post("/index-document", json={"email": OUTRO, "content": "documento do Douglas"})

        cliente.delete(f"/reset/{EMAIL}")

        db = main.SessionLocal()
        try:
            assert db.query(main.DocumentChunk).filter_by(user_email=OUTRO).count() == 1
        finally:
            db.close()
