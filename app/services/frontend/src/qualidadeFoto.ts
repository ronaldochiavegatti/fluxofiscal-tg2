/**
 * Checagem de qualidade da foto no próprio celular, antes do envio (issue 100).
 *
 * Mesmas contas e mesmos cortes de `documents/app/qualidade.py`: os dois
 * precisam mudar juntos. Aqui a foto ruim nem sai do aparelho, então não
 * custa upload, OCR nem chamada ao Gemini. A redução feita pelo canvas não é
 * idêntica à do Pillow, então os números diferem um pouco; o servidor confere
 * de novo e tem a palavra final.
 */

export const LADO_ANALISE = 1000;
export const MENOR_LADO_MINIMO = 400;
export const NITIDEZ_MINIMA = 10;
export const RAZAO_NITIDEZ_MINIMA = 1.1;
export const BRILHO_MINIMO = 25;
export const BRILHO_MAXIMO = 250;
export const CONTRASTE_MINIMO = 4;

export type MotivoFotoRuim = "pequena" | "tremida" | "escura" | "estourada" | "sem_contraste" | "invalida";

export type AvaliacaoFoto = {
  legivel: boolean;
  motivo: MotivoFotoRuim | null;
  nitidez: number;
  razaoNitidez: number;
  brilho: number;
  contraste: number;
  largura: number;
  altura: number;
};

export const MENSAGENS: Record<MotivoFotoRuim, string> = {
  pequena: "A foto tem pouca resolução para ler as letras da nota.",
  tremida: "A foto está tremida ou fora de foco.",
  escura: "A foto está escura demais para ler.",
  estourada: "A foto está clara demais, com reflexo ou flash.",
  sem_contraste: "Não aparece texto na foto.",
  invalida: "Não foi possível abrir a imagem.",
};

export const DICAS: Record<MotivoFotoRuim, string> = {
  pequena: "Chegue mais perto da nota e use a câmera traseira, sem zoom digital.",
  tremida: "Apoie os cotovelos, toque na nota para focar e espere um instante antes de fotografar.",
  escura: "Procure um lugar iluminado. Luz de janela funciona melhor que a da tela.",
  estourada: "Desligue o flash e afaste a nota da luz direta. O reflexo apaga o texto.",
  sem_contraste: "Confira se a lente está livre e se a nota inteira aparece no enquadramento.",
  invalida: "Tire a foto de novo ou envie o PDF da nota.",
};

const LAPLACIANO = [0, 1, 0, 1, -4, 1, 0, 1, 0];
const SUAVIZACAO = [1, 2, 1, 2, 4, 2, 1, 2, 1];

/** Convolução 3x3 como o `ImageFilter.Kernel` do Pillow: borda copiada, resultado arredondado em 0..255. */
function convoluir(px: Uint8ClampedArray, l: number, a: number, k: number[], escala: number, deslocamento: number) {
  const saida = new Uint8ClampedArray(px);
  for (let y = 1; y < a - 1; y++) {
    for (let x = 1; x < l - 1; x++) {
      let soma = 0;
      for (let j = -1; j <= 1; j++) {
        for (let i = -1; i <= 1; i++) {
          soma += px[(y + j) * l + (x + i)] * k[(j + 1) * 3 + (i + 1)];
        }
      }
      saida[y * l + x] = Math.round(soma / escala + deslocamento);
    }
  }
  return saida;
}

function media(px: Uint8ClampedArray) {
  let s = 0;
  for (let i = 0; i < px.length; i++) s += px[i];
  return s / px.length;
}

function variancia(px: Uint8ClampedArray) {
  const m = media(px);
  let s = 0;
  for (let i = 0; i < px.length; i++) s += (px[i] - m) ** 2;
  return s / px.length;
}

export function motivoDaRecusa(m: Omit<AvaliacaoFoto, "legivel" | "motivo">): MotivoFotoRuim | null {
  if (Math.min(m.largura, m.altura) < MENOR_LADO_MINIMO) return "pequena";
  if (m.brilho < BRILHO_MINIMO) return "escura";
  if (m.brilho > BRILHO_MAXIMO) return "estourada";
  if (m.contraste < CONTRASTE_MINIMO) return "sem_contraste";
  if (m.nitidez < NITIDEZ_MINIMA || m.razaoNitidez < RAZAO_NITIDEZ_MINIMA) return "tremida";
  return null;
}

/**
 * Avalia tons de cinza já reduzidos (`cinza`, `l` x `a`). `largura` e
 * `altura` são as da foto original, que decidem o motivo "pequena".
 */
export function avaliarCinza(
  cinza: Uint8ClampedArray,
  l: number,
  a: number,
  largura: number,
  altura: number,
): AvaliacaoFoto {
  const brilho = media(cinza);
  const contraste = Math.sqrt(variancia(cinza));
  const nitidez = variancia(convoluir(cinza, l, a, LAPLACIANO, 1, 128));
  const suavizada = variancia(convoluir(convoluir(cinza, l, a, SUAVIZACAO, 16, 0), l, a, LAPLACIANO, 1, 128));
  const medidas = {
    nitidez: Math.round(nitidez * 10) / 10,
    razaoNitidez: Math.round((nitidez / Math.max(suavizada, 1e-6)) * 100) / 100,
    brilho: Math.round(brilho * 10) / 10,
    contraste: Math.round(contraste * 10) / 10,
    largura,
    altura,
  };
  const motivo = motivoDaRecusa(medidas);
  return { legivel: motivo === null, motivo, ...medidas };
}

/** RGBA do canvas para cinza, com os pesos do modo "L" do Pillow. */
export function rgbaParaCinza(rgba: Uint8ClampedArray): Uint8ClampedArray {
  const cinza = new Uint8ClampedArray(rgba.length / 4);
  for (let i = 0; i < cinza.length; i++) {
    cinza[i] = (rgba[i * 4] * 299 + rgba[i * 4 + 1] * 587 + rgba[i * 4 + 2] * 114) / 1000;
  }
  return cinza;
}

export const ehFoto = (arquivo: File) =>
  arquivo.type.startsWith("image/") || /\.(png|jpe?g|tiff?)$/i.test(arquivo.name);

/**
 * Lê a foto no canvas e avalia. Devolve `null` quando o navegador não tem
 * como medir (sem `createImageBitmap` ou sem canvas): aí o envio segue e só o
 * servidor confere.
 */
export async function avaliarArquivo(arquivo: File): Promise<AvaliacaoFoto | null> {
  if (typeof createImageBitmap !== "function" || typeof document === "undefined") return null;
  let bitmap: ImageBitmap;
  try {
    bitmap = await createImageBitmap(arquivo, { imageOrientation: "from-image" });
  } catch {
    return { ...avaliarVazio(), motivo: "invalida" };
  }
  try {
    const escala = Math.min(1, LADO_ANALISE / Math.max(bitmap.width, bitmap.height));
    const l = Math.max(3, Math.round(bitmap.width * escala));
    const a = Math.max(3, Math.round(bitmap.height * escala));
    const canvas = document.createElement("canvas");
    canvas.width = l;
    canvas.height = a;
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    if (!ctx) return null;
    ctx.drawImage(bitmap, 0, 0, l, a);
    const cinza = rgbaParaCinza(ctx.getImageData(0, 0, l, a).data);
    return avaliarCinza(cinza, l, a, bitmap.width, bitmap.height);
  } catch {
    return null;
  } finally {
    bitmap.close();
  }
}

function avaliarVazio(): AvaliacaoFoto {
  return { legivel: false, motivo: null, nitidez: 0, razaoNitidez: 0, brilho: 0, contraste: 0, largura: 0, altura: 0 };
}
