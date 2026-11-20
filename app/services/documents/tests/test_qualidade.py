"""Barreira de qualidade da foto (#100).

Cenários:
  - Foto nítida de nota passa e segue para a leitura.
  - Foto tremida, escura, estourada, sem texto ou pequena demais é recusada
    antes de gravar o arquivo e de chamar o Gemini, com o motivo e uma dica.
  - "Enviar mesmo assim" (forcar_leitura) lê a foto recusada.
  - PDF e texto não passam pela barreira.
"""

import io

import pytest
from PIL import Image, ImageDraw, ImageFilter

from app import main
from app.qualidade import (
    DICAS,
    MENSAGENS,
    AvaliacaoFoto,
    avaliar_foto,
    medir,
    motivo_da_recusa,
)
from tests.conftest import EMAIL


def _nota(largura: int = 1200, altura: int = 900) -> Image.Image:
    """Uma "nota" sintética: papel claro com 40 linhas de texto escuro."""
    img = Image.new("L", (largura, altura), 245)
    desenho = ImageDraw.Draw(img)
    for i in range(40):
        desenho.text(
            (40, 20 + i * 21),
            f"ITEM {i:02d}  PRODUTO  QTD 1  VALOR R$ {i * 3 + 1},90  CNPJ 12.345.678/0001-95",
            fill=20,
        )
    return img


def _bytes(img: Image.Image, formato: str = "PNG") -> bytes:
    saida = io.BytesIO()
    img.save(saida, formato)
    return saida.getvalue()


NITIDA = _bytes(_nota())


class TestAvaliacao:
    def test_nota_nitida_e_legivel(self):
        a = avaliar_foto(NITIDA)

        assert a.legivel is True
        assert a.motivo is None
        assert a.razao_nitidez > 2

    @pytest.mark.parametrize(
        ("imagem", "motivo"),
        [
            (_nota().filter(ImageFilter.GaussianBlur(6)), "tremida"),
            (_nota().resize((300, 225)), "pequena"),
            (Image.new("L", (1200, 900), 5), "escura"),
            (Image.new("L", (1200, 900), 255), "estourada"),
            (Image.new("L", (1200, 900), 128), "sem_contraste"),
        ],
    )
    def test_foto_ruim_e_recusada_com_motivo(self, imagem, motivo):
        a = avaliar_foto(_bytes(imagem))

        assert a.legivel is False
        assert a.motivo == motivo
        assert MENSAGENS[motivo]
        assert DICAS[motivo]

    def test_arquivo_que_nao_e_imagem(self):
        a = avaliar_foto(b"isto nao e uma imagem")

        assert (a.legivel, a.motivo) == (False, "invalida")

    def test_jpeg_grande_e_reduzido_antes_de_medir(self):
        grande = _bytes(_nota().resize((4000, 3000)), "JPEG")

        a = medir(grande)

        assert (a.largura, a.altura) == (4000, 3000)
        assert a.legivel is True

    def test_orientacao_exif_nao_muda_o_tamanho_medido(self):
        img = _nota().convert("RGB")
        exif = Image.Exif()
        exif[0x0112] = 6  # girada 90 graus
        saida = io.BytesIO()
        img.save(saida, "JPEG", exif=exif)

        a = medir(saida.getvalue())

        assert (a.largura, a.altura) == (1200, 900)

    def test_ordem_dos_motivos_mostra_o_mais_facil_de_corrigir(self):
        # Pequena e escura ao mesmo tempo: "chegue mais perto" vem antes.
        a = AvaliacaoFoto(True, None, 10.0, 1.0, 5.0, 0.0, 300, 200)

        assert motivo_da_recusa(a) == "pequena"


def enviar_imagem(cliente, conteudo: bytes, nome: str = "foto.png", **extra):
    return cliente.post(
        "/upload",
        files={"file": (nome, conteudo, "image/png")},
        data={"email": EMAIL, **extra},
    )


class TestUploadComBarreira:
    def test_foto_ruim_nao_e_lida_nem_gravada(self, cliente, pasta_de_upload, monkeypatch):
        def _nao_deveria_ler(*_a, **_k):
            raise AssertionError("a foto ruim chegou à extração")

        monkeypatch.setattr(main.processamento, "processar_arquivo", _nao_deveria_ler)
        borrada = _bytes(_nota().filter(ImageFilter.GaussianBlur(6)))

        resposta = enviar_imagem(cliente, borrada)

        assert resposta.status_code == 422
        detalhe = resposta.json()["detail"]
        assert detalhe["codigo"] == "foto_ilegivel"
        assert detalhe["motivo"] == "tremida"
        assert detalhe["mensagem"] == MENSAGENS["tremida"]
        assert detalhe["dica"] == DICAS["tremida"]
        assert detalhe["medidas"]["razao_nitidez"] < 1.1
        assert list(pasta_de_upload.iterdir()) == []

    def test_recusa_conta_na_metrica(self, cliente):
        antes = main.fotos_recusadas_total.labels(motivo="escura")._value.get()

        enviar_imagem(cliente, _bytes(Image.new("L", (1200, 900), 5)))

        assert main.fotos_recusadas_total.labels(motivo="escura")._value.get() == antes + 1

    def test_forcar_leitura_le_a_foto_recusada(self, cliente):
        borrada = _bytes(_nota().filter(ImageFilter.GaussianBlur(6)))

        resposta = enviar_imagem(cliente, borrada, forcar_leitura="true")

        assert resposta.status_code == 200
        assert "structured_data" in resposta.json()

    def test_foto_boa_segue_para_a_leitura(self, cliente):
        resposta = enviar_imagem(cliente, NITIDA)

        assert resposta.status_code == 200
        assert "structured_data" in resposta.json()

    def test_pdf_e_texto_nao_passam_pela_barreira(self, cliente, monkeypatch):
        monkeypatch.setattr(
            main,
            "avaliar_foto",
            lambda *_a: pytest.fail("a barreira avaliou um arquivo que não é foto"),
        )

        resposta = cliente.post(
            "/upload",
            files={"file": ("nota.txt", b"VALOR TOTAL R$ 10,00", "text/plain")},
            data={"email": EMAIL},
        )

        assert resposta.status_code == 200
