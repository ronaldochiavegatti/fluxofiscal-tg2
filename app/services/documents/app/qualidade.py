"""Barreira de qualidade da foto antes do OCR e do Gemini (#100).

Para imagem, o Gemini roda em paralelo com o OCR (ver `processamento`), e cada
foto tremida ou ilegível pagava uma chamada que não tinha como dar certo. Estas
medidas custam alguns milissegundos sobre a imagem reduzida e decidem antes.

O que a calibração mostrou (40 fotos e renderizações do lote de teste, mais 25
versões degradadas de cada, lidas pelo Tesseract):

- **borrão e tremido** são o que impede a leitura. A nitidez absoluta
  (variância do Laplaciano) depende de quanto texto há na imagem: uma NFS-e
  cheia de letras continua "nítida" mesmo borrada. Por isso a decisão usa
  também a **razão de nitidez**: quanto a variância cai quando a própria foto
  é suavizada de novo. Foto nítida perde muito (razão alta); foto já borrada
  quase não muda (razão perto de 1);
- **escuridão e pouco contraste**, por si, quase não atrapalham: o Tesseract
  binariza a imagem e leu todas as versões escurecidas até 20% do brilho. Só
  o extremo (lente tapada, foto preta ou branca) é barrado;
- **resolução**: com o menor lado em 300 px nenhuma nota foi lida.

Depois, os cortes de nitidez foram recalibrados contra o próprio Gemini, que
lê bem mais borrado que o Tesseract (desfoque de raio 4 numa foto de cupom,
raio 6 numa DANFE). Com borrão forte, o Gemini não falha: devolve valores
plausíveis e errados (R$ 1.087 e R$ 1.450 para uma nota de R$ 1.557,80).
A barreira, então, protege também o dado, não só o custo. Com razão < 1,1 ela
barra todos os desfoques fortes que o Gemini errou ou não leu. Ainda passa
parte do tremido de movimento forte, e uma DANFE com desfoque de raio 6, que o
Gemini leu, seria recusada: por isso "enviar mesmo assim" existe.

O frontend repete as mesmas contas antes do envio
(`frontend/src/qualidadeFoto.ts`); os dois precisam mudar juntos.
"""

from __future__ import annotations

import io
from dataclasses import asdict, dataclass

from PIL import Image, ImageFilter, ImageOps, ImageStat, UnidentifiedImageError

# Lado maior da imagem analisada. A medida fica comparável entre fotos de 2 MP
# e de 48 MP porque todas são reduzidas para a mesma escala antes.
LADO_ANALISE = 1000

MENOR_LADO_MINIMO = 400
NITIDEZ_MINIMA = 10.0
RAZAO_NITIDEZ_MINIMA = 1.1
BRILHO_MINIMO = 25.0
BRILHO_MAXIMO = 250.0
CONTRASTE_MINIMO = 4.0

# Kernels explícitos (e não `GaussianBlur`) para o frontend reproduzir a mesma
# conta. O deslocamento de 128 no Laplaciano mantém o sinal: sem ele, toda
# resposta negativa viraria 0 e a variância sairia pela metade.
_LAPLACIANO = ImageFilter.Kernel((3, 3), [0, 1, 0, 1, -4, 1, 0, 1, 0], scale=1, offset=128)
_SUAVIZACAO = ImageFilter.Kernel((3, 3), [1, 2, 1, 2, 4, 2, 1, 2, 1], scale=16)

MENSAGENS = {
    "pequena": "A foto tem pouca resolução para ler as letras da nota.",
    "tremida": "A foto está tremida ou fora de foco.",
    "escura": "A foto está escura demais para ler.",
    "estourada": "A foto está clara demais, com reflexo ou flash.",
    "sem_contraste": "Não aparece texto na foto.",
    "invalida": "Não foi possível abrir a imagem.",
}

DICAS = {
    "pequena": "Chegue mais perto da nota e use a câmera traseira, sem zoom digital.",
    "tremida": "Apoie os cotovelos, toque na nota para focar e espere um instante antes de fotografar.",
    "escura": "Procure um lugar iluminado. Luz de janela funciona melhor que a da tela.",
    "estourada": "Desligue o flash e afaste a nota da luz direta. O reflexo apaga o texto.",
    "sem_contraste": "Confira se a lente está livre e se a nota inteira aparece no enquadramento.",
    "invalida": "Tire a foto de novo ou envie o PDF da nota.",
}


@dataclass(frozen=True)
class AvaliacaoFoto:
    legivel: bool
    motivo: str | None
    nitidez: float
    razao_nitidez: float
    brilho: float
    contraste: float
    largura: int
    altura: int

    def como_dict(self) -> dict:
        return asdict(self)


def _variancia_laplaciano(imagem: Image.Image) -> float:
    return float(ImageStat.Stat(imagem.filter(_LAPLACIANO)).var[0])


def medir(conteudo: bytes) -> AvaliacaoFoto:
    """Mede a foto sem decidir nada. Ver `avaliar_foto` para a decisão."""
    try:
        imagem = Image.open(io.BytesIO(conteudo))
        largura, altura = imagem.size
        # JPEG: decodifica já reduzido (draft), sem abrir 48 MP inteiros.
        imagem.draft("L", (LADO_ANALISE, LADO_ANALISE))
        cinza = ImageOps.exif_transpose(imagem).convert("L")
    except (UnidentifiedImageError, OSError, ValueError):
        return AvaliacaoFoto(False, "invalida", 0.0, 0.0, 0.0, 0.0, 0, 0)

    cinza.thumbnail((LADO_ANALISE, LADO_ANALISE))
    tons = ImageStat.Stat(cinza)
    nitidez = _variancia_laplaciano(cinza)
    suavizada = _variancia_laplaciano(cinza.filter(_SUAVIZACAO))
    return AvaliacaoFoto(
        legivel=True,
        motivo=None,
        nitidez=round(nitidez, 1),
        razao_nitidez=round(nitidez / max(suavizada, 1e-6), 2),
        brilho=round(tons.mean[0], 1),
        contraste=round(tons.stddev[0], 1),
        largura=largura,
        altura=altura,
    )


def motivo_da_recusa(m: AvaliacaoFoto) -> str | None:
    """O primeiro problema encontrado, ou None se vale a pena ler.

    A ordem importa: é o motivo que o usuário vê, então o mais fácil de
    corrigir (chegar perto, acender a luz) vem antes do tremido, que muitas
    vezes é consequência dos outros.
    """
    if m.motivo == "invalida":
        return "invalida"
    if min(m.largura, m.altura) < MENOR_LADO_MINIMO:
        return "pequena"
    if m.brilho < BRILHO_MINIMO:
        return "escura"
    if m.brilho > BRILHO_MAXIMO:
        return "estourada"
    if m.contraste < CONTRASTE_MINIMO:
        return "sem_contraste"
    if m.nitidez < NITIDEZ_MINIMA or m.razao_nitidez < RAZAO_NITIDEZ_MINIMA:
        return "tremida"
    return None


def avaliar_foto(conteudo: bytes) -> AvaliacaoFoto:
    """Diz se vale a pena ler a foto e, se não vale, por quê."""
    m = medir(conteudo)
    motivo = motivo_da_recusa(m)
    if motivo is None:
        return m
    return AvaliacaoFoto(
        False,
        motivo,
        m.nitidez,
        m.razao_nitidez,
        m.brilho,
        m.contraste,
        m.largura,
        m.altura,
    )
