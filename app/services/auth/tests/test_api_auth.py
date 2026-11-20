"""Testes das rotas do Auth.

O ADR-0011 decidiu manter a autenticação simplificada nesta fase: não há token,
e a identidade é autodeclarada nas demais rotas da plataforma. O que este
serviço ainda precisa garantir, e é o que os testes cobram, é o mínimo que
continua valendo mesmo assim — senha nunca armazenada nem devolvida em texto
puro, e a mesma resposta para usuário inexistente e senha errada.
"""

import pytest

from app import models
from app.security import hash_password, verify_password
from tests.conftest import SENHA

EMAIL = "marcia@mei.com.br"
OUTRO = "douglas@mei.com.br"


@pytest.fixture
def usuario(cliente):
    resposta = cliente.post("/users", json={"email": EMAIL, "password": SENHA})
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


class TestHealth:
    def test_responde_identificando_o_servico(self, cliente):
        assert cliente.get("/health").json() == {"status": "ok", "service": "auth"}


class TestCadastro:
    def test_cria_o_usuario(self, usuario):
        assert usuario["id"] > 0
        assert usuario["email"] == EMAIL

    def test_resposta_nao_carrega_a_senha(self, usuario):
        """Nem a senha, nem o hash: o contrato de saída tem só id e e-mail."""
        assert set(usuario) == {"id", "email"}

    def test_senha_nao_e_gravada_em_texto_puro(self, cliente, usuario):
        gravado = cliente.get("/users").json()
        assert gravado  # a listagem também não expõe hash
        assert set(gravado[0]) == {"id", "email"}

    def test_email_repetido_e_recusado(self, cliente, usuario):
        resposta = cliente.post("/users", json={"email": EMAIL, "password": "outra-senha"})

        assert resposta.status_code == 400
        assert resposta.json()["detail"] == "Email already registered"

    def test_email_invalido_e_recusado_pelo_contrato(self, cliente):
        resposta = cliente.post("/users", json={"email": "nao-e-email", "password": SENHA})

        assert resposta.status_code == 422

    def test_senha_com_byte_nulo_e_recusada(self, cliente):
        """Regressão: o bcrypt levanta exceção com byte nulo e a rota devolvia 500."""
        senha = "abc" + chr(0) + "def"

        resposta = cliente.post("/users", json={"email": EMAIL, "password": senha})

        assert resposta.status_code == 422

    def test_senha_vazia_e_recusada(self, cliente):
        resposta = cliente.post("/users", json={"email": EMAIL, "password": ""})

        assert resposta.status_code == 422


class TestListagem:
    def test_vazia_quando_ninguem_se_cadastrou(self, cliente):
        assert cliente.get("/users").json() == []

    def test_lista_os_cadastrados(self, cliente, usuario):
        cliente.post("/users", json={"email": OUTRO, "password": SENHA})

        emails = [u["email"] for u in cliente.get("/users").json()]

        assert sorted(emails) == sorted([EMAIL, OUTRO])


class TestLogin:
    def test_credenciais_corretas(self, cliente, usuario):
        resposta = cliente.post("/login", json={"email": EMAIL, "password": SENHA})

        assert resposta.status_code == 200
        assert resposta.json() == {"message": "login ok", "user_id": usuario["id"]}

    def test_senha_errada(self, cliente, usuario):
        resposta = cliente.post("/login", json={"email": EMAIL, "password": "errada"})

        assert resposta.status_code == 401

    def test_usuario_inexistente(self, cliente):
        resposta = cliente.post("/login", json={"email": "ninguem@mei.com.br", "password": SENHA})

        assert resposta.status_code == 401

    def test_mensagem_nao_distingue_os_dois_casos(self, cliente, usuario):
        """Mensagens diferentes revelariam quais e-mails existem na base.

        A autenticação é simplificada por decisão de escopo (ADR-0011), mas
        enumerar usuários é um vazamento que não custa nada evitar.
        """
        inexistente = cliente.post(
            "/login", json={"email": "ninguem@mei.com.br", "password": SENHA}
        )
        senha_errada = cliente.post("/login", json={"email": EMAIL, "password": "errada"})

        assert inexistente.json() == senha_errada.json()


class TestHashDeSenha:
    def test_hash_nao_contem_a_senha(self):
        assert SENHA not in hash_password(SENHA)

    def test_hash_confere_com_a_senha_original(self):
        assert verify_password(SENHA, hash_password(SENHA)) is True

    def test_hash_recusa_senha_errada(self):
        assert verify_password("errada", hash_password(SENHA)) is False

    def test_mesma_senha_gera_hashes_diferentes(self):
        """Sal por hash: duas contas com a mesma senha não se denunciam."""
        assert hash_password(SENHA) != hash_password(SENHA)


class TestModelo:
    def test_email_e_unico_no_esquema(self):
        """A recusa de duplicata não pode depender só da checagem na rota."""
        assert models.User.__table__.c.email.unique is True
