"""Gera as notas de teste no layout oficial, em ambiente de homologação.

Notas 01 a 12: o teste controlado do artigo (protocolo abaixo; "conjunto":
"artigo" no gabarito). Notas 13 a 52: 40 notas extras no mesmo padrão, para
testar a aplicação (20 vendas que continuam a numeração do MEI, 9 NF-e, 5 NFS-e
e 6 NFC-e de compra; "conjunto": "extra").

Protocolo (Metodologia do artigo): 12 notas nos formatos PNG, JPG, PDF e TXT —
uma delas um recibo com subtotal, desconto e total, levemente rotacionado e
com ruído visual — avaliadas pelo acerto exato de valor total, data de emissão
e CNPJ; e 5 perguntas sobre regras do MEI, redigidas com palavras diferentes
das usadas nos trechos da base.

Cada operação usa o documento que a norma prevê:
- Venda de serviço pelo MEI → DANFSe do padrão nacional (NFS-e Nacional,
  obrigatória para o MEI prestador de serviços desde 09/2023).
- Compra de mercadoria → DANFE da NF-e modelo 55 (leiaute do Anexo II do MOC).
- Compra de serviço → DANFSe, com o MEI como tomador.
- Compra no varejo com desconto → DANFE NFC-e modelo 65 (cupom), fotografado.

Todas são emitidas em ambiente de HOMOLOGAÇÃO / produção restrita, com a tarja
"SEM VALOR FISCAL" e o nome do destinatário que a SEFAZ exige nesse ambiente.
Chaves de acesso seguem a estrutura oficial com DV módulo 11, mas nenhuma nota
foi transmitida: são documentos de teste, não documentos fiscais.

Uso: python gerar.py   (requer Pillow e qrcode; fontes Arial do Windows)
Determinístico: a mesma execução gera os mesmos arquivos.
"""

import hashlib
import json
import random
from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageFilter, ImageFont

AQUI = Path(__file__).parent
FONTES = Path("C:/Windows/Fonts")
random.seed(2026)

HOMOLOGACAO = "EMITIDA EM AMBIENTE DE HOMOLOGAÇÃO - SEM VALOR FISCAL"
# xNome que a SEFAZ exige para o destinatário de NF-e/NFC-e em homologação.
DEST_HOMOLOGACAO = "NF-E EMITIDA EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL"

# ---------------------------------------------------------------------------
# Identificadores fiscais
# ---------------------------------------------------------------------------


def dv_mod11(numero: str, peso_max: int = 9) -> int:
    soma, peso = 0, 2
    for digito in reversed(numero):
        soma += int(digito) * peso
        peso = 2 if peso == peso_max else peso + 1
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def cnpj(base8: str, filial: str = "0001") -> str:
    """CNPJ fictício com dígitos verificadores válidos."""
    s = base8 + filial
    s += str(dv_mod11(s))
    s += str(dv_mod11(s))
    return f"{s[:2]}.{s[2:5]}.{s[5:8]}/{s[8:12]}-{s[12:]}"


def so_digitos(texto: str) -> str:
    return "".join(c for c in texto if c.isdigit())


def chave_nfe(uf: str, data: str, cnpj_emit: str, modelo: str, serie: int, numero: int) -> str:
    """Chave de 44 dígitos: cUF AAMM CNPJ mod série nNF tpEmis cNF cDV (MOC 7.0)."""
    corpo = (uf + data[2:4] + data[5:7] + so_digitos(cnpj_emit) + modelo + f"{serie:03d}"
             + f"{numero:09d}" + "1" + f"{random.randrange(10**8):08d}")
    return corpo + str(dv_mod11(corpo))


def chave_nfse(mun: str, cnpj_emit: str, numero: int, data: str) -> str:
    """Chave de 50 dígitos da NFS-e Nacional: cMun, ambiente gerador, tipo de
    inscrição, CNPJ, nNFSe, AAMM, código aleatório e DV."""
    corpo = (mun + "1" + "2" + so_digitos(cnpj_emit) + f"{numero:013d}" + data[2:4] + data[5:7]
             + f"{random.randrange(10**9):09d}")
    return corpo + str(dv_mod11(corpo))


def agrupar(chave: str) -> str:
    return " ".join(chave[i:i + 4] for i in range(0, len(chave), 4))


def brl(v: float, prefixo: bool = True) -> str:
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}" if prefixo else s


def data_br(iso: str) -> str:
    a, m, d = iso.split("-")
    return f"{d}/{m}/{a}"


# ---------------------------------------------------------------------------
# Partes (todas fictícias; CNPJs com DV válido que não pertencem a ninguém)
# ---------------------------------------------------------------------------

SAO_PAULO = ("São Paulo", "SP", "3550308")
MEI = {
    "nome": "Ronaldo Chiavegatti Serviços de TI MEI", "cnpj": "12.345.678/0001-90",
    "im": "1.234.567-8", "fone": "(11) 3456-7890", "email": "contato@rcti.com.br",
    "end": "Rua das Palmeiras, 120 - Sala 4", "bairro": "Vila Mariana", "cep": "04101-000",
}


def empresa(nome, base8, end, bairro, cep, fone, ie="", im="", email=""):
    return {"nome": nome, "cnpj": cnpj(base8), "end": end, "bairro": bairro, "cep": cep,
            "fone": fone, "ie": ie, "im": im, "email": email}


CLIENTES = {
    "A": empresa("Padaria Pão Dourado Ltda", "31415926", "Av. Domingos de Morais, 1500", "Vila Mariana",
                 "04010-100", "(11) 5571-2233", im="2.345.678-9", email="financeiro@paodourado.com.br"),
    "B": empresa("Clínica Sorriso Pleno Ltda", "27182818", "Rua Vergueiro, 3185 - Cj 52", "Vila Mariana",
                 "04101-300", "(11) 5084-9911", im="3.456.789-0", email="adm@sorrisopleno.com.br"),
    "C": empresa("Auto Peças Rota 66 Ltda", "16180339", "Av. Jabaquara, 880", "Saúde", "04046-100",
                 "(11) 5017-4466", im="4.567.890-1", email="compras@rota66pecas.com.br"),
    "D": empresa("Escola de Idiomas Fale Bem Ltda", "14142135", "Rua Sena Madureira, 410", "Vila Clementino",
                 "04021-000", "(11) 5539-7788", im="5.678.901-2", email="secretaria@falebem.com.br"),
}
FORNECEDORES = {
    "E": empresa("InfoParts Componentes Eletrônicos Ltda", "57721566", "Rua Santa Ifigênia, 302",
                 "Santa Ifigênia", "01207-000", "(11) 3221-5050", ie="110.042.490.114"),
    "F": empresa("Ergo Móveis para Escritório Ltda", "69314718", "Av. Ricardo Jafet, 2100", "Ipiranga",
                 "04260-020", "(11) 2063-1414", ie="114.928.335.110"),
    "G": empresa("Coworking Espaço Central Ltda", "30102999", "Rua Domingos de Morais, 2781 - 8º andar",
                 "Vila Mariana", "04035-001", "(11) 5085-3030", im="6.789.012-3",
                 email="faturamento@espacocentral.com.br"),
    "H": empresa("Papelaria e Gráfica Bom Preço Ltda", "41421356", "Rua Loefgren, 1020", "Vila Clementino",
                 "04040-001", "(11) 5574-6060", ie="116.330.871.119"),
}

# Código de Tributação Nacional (subitens 1.xx da lista da LC 116/2003).
CTN = {
    "01.01.01": "Análise e desenvolvimento de sistemas",
    "01.02.01": "Programação",
    "01.06.01": "Assessoria e consultoria em informática",
    "01.07.01": "Suporte técnico em informática, inclusive instalação, configuração e manutenção "
                "de programas de computação e bancos de dados",
    "03.03.01": "Exploração de salões de festas, centro de convenções, escritórios virtuais, stands, "
                "quadras esportivas, estádios, ginásios, auditórios, casas de espetáculos e congêneres",
}

# (arquivo, data, valor, cliente, código de tributação, descrição)
VENDAS = [
    ("01_venda_nfse.png", "2026-01-14", 3200.00, "A", "01.01.01", "Desenvolvimento de site institucional responsivo com painel administrativo."),
    ("02_venda_nfse.jpg", "2026-02-20", 4750.00, "B", "01.01.01", "Desenvolvimento de sistema de agendamento online de consultas."),
    ("03_venda_nfse.pdf", "2026-03-11", 5180.50, "A", "01.07.01", "Manutenção mensal de sistemas e banco de dados - competências jan a mar/2026."),
    ("04_venda_nfse.txt", "2026-04-08", 2940.00, "C", "01.07.01", "Suporte técnico, instalação e configuração de rede e estações de trabalho."),
    ("05_venda_nfse.png", "2026-05-22", 6300.00, "B", "01.01.01", "Integração do sistema de agendamento com gateway de pagamentos."),
    ("06_venda_nfse.pdf", "2026-06-17", 4125.75, "D", "01.01.01", "Desenvolvimento de plataforma de cursos online - módulo 1."),
    ("07_venda_nfse.jpg", "2026-07-09", 7480.00, "A", "01.02.01", "Programação de aplicativo de pedidos para delivery (Android e iOS)."),
    ("08_venda_nfse.txt", "2026-08-26", 5600.00, "C", "01.06.01", "Consultoria em segurança da informação e adequação à LGPD."),
]

# ---------------------------------------------------------------------------
# Notas extras (13 a 52) para testar a aplicação — fora do protocolo do artigo
# ---------------------------------------------------------------------------

CLIENTES_EXTRA = {
    "I": empresa("Pet Shop Quatro Patas Ltda", "17320508", "Rua Afonso Celso, 1221", "Vila Mariana", "04119-061",
           "(11) 5579-1010", im="7.890.123-4", email="contato@quatropataspet.com.br"),
    "J": empresa("Construtora Alicerce Forte Ltda", "22360679", "Av. Ibirapuera, 2332 - 7º andar", "Moema",
           "04028-002", "(11) 5051-2020", im="8.901.234-5", email="obras@alicerceforte.com.br"),
    "K": empresa("Academia Corpo em Movimento Ltda", "26457513", "Rua Tutóia, 655", "Paraíso", "04007-003",
           "(11) 3884-3030", im="9.012.345-6", email="gerencia@corpoemmovimento.com.br"),
    "L": empresa("Restaurante Sabor da Terra Ltda", "28284271", "Rua Joaquim Távora, 1015", "Vila Mariana",
           "04015-012", "(11) 5083-4040", im="1.123.456-7", email="adm@sabordaterra.com.br"),
    "M": empresa("Escritório Contábil Exato Ltda", "33166247", "Rua Pedro de Toledo, 980 - Cj 31",
           "Vila Clementino", "04039-002", "(11) 5571-5050", im="2.234.567-8",
           email="atendimento@contabilexato.com.br"),
    "N": empresa("Loja de Roupas Estilo Urbano Ltda", "36055512", "Rua Teodoro Sampaio, 1810", "Pinheiros",
           "05406-150", "(11) 3062-6060", im="3.345.678-9", email="loja@estilourbano.com.br"),
    "O": empresa("Imobiliária Chave Certa Ltda", "38729833", "Av. Jabaquara, 1469", "Mirandópolis", "04045-002",
           "(11) 5589-7070", im="4.456.789-0", email="locacao@chavecerta.com.br"),
    "P": empresa("Laboratório Diagnóstico Vital Ltda", "42426406", "Rua Borges Lagoa, 1080", "Vila Clementino",
           "04038-002", "(11) 5549-8080", im="5.567.890-1", email="ti@labvital.com.br"),
}

FORNECEDORES_EXTRA = {
    "Q": empresa("TecnoNet Distribuidora de Informática Ltda", "45175395", "Rua dos Timbiras, 466",
           "Santa Ifigênia", "01208-010", "(11) 3331-1111", ie="111.203.450.117"),
    "R": empresa("Rede Fibra Conecta Telecom Ltda", "47720958", "Av. Paulista, 1048 - 10º andar", "Bela Vista",
           "01310-100", "(11) 3289-2222", im="6.678.901-2", email="faturas@fibraconecta.com.br"),
    "S": empresa("Nuvem Segura Hospedagem de Dados Ltda", "50663151", "Rua Funchal, 418 - 5º andar",
           "Vila Olímpia", "04551-060", "(11) 3045-3333", im="7.789.012-3",
           email="cobranca@nuvemsegura.com.br"),
    "T": empresa("Contabilidade Prática Assessoria Ltda", "52705749", "Rua Cubatão, 320 - Cj 12", "Paraíso",
           "04013-001", "(11) 3051-4444", im="8.890.123-4", email="mei@contabilpratica.com.br"),
    "U": empresa("Escola Digital Cursos Livres Ltda", "55319832", "Rua Vergueiro, 1421 - 3º andar", "Paraíso",
           "04101-000", "(11) 3271-5555", im="9.901.234-5", email="matriculas@escoladigital.com.br"),
    "V": empresa("Kalunga Express Suprimentos Ltda", "57735026", "Rua Domingos de Morais, 2564", "Vila Mariana",
           "04036-100", "(11) 5574-6666", ie="112.554.098.110"),
    "W": empresa("Mercado Bom Dia Vila Mariana Ltda", "61803398", "Rua França Pinto, 845", "Vila Mariana",
           "04016-034", "(11) 5571-7777", ie="113.665.209.113"),
    "X": empresa("Eletro Center Utilidades Ltda", "64575131", "Av. Sen. Casemiro da Rocha, 950", "Mirandópolis",
           "04047-002", "(11) 5581-8888", ie="115.776.310.116"),
    "Y": empresa("Gráfica Express Impressão Digital Ltda", "66820148", "Rua Pelotas, 220", "Vila Mariana",
           "04012-000", "(11) 5539-9999", ie="117.887.421.119"),
}

CTN_EXTRA = {
    "01.03.01": "Processamento, armazenamento ou hospedagem de dados, textos, imagens, vídeos, páginas "
                "eletrônicas, aplicativos e sistemas de informação, entre outros formatos, e congêneres",
    "17.19.01": "Contabilidade, inclusive serviços técnicos e auxiliares",
    "08.02.01": "Instrução, treinamento, orientação pedagógica e educacional, avaliação de conhecimentos "
                "de qualquer natureza",
    "01.08.01": "Planejamento, confecção, manutenção e atualização de páginas eletrônicas",
}

# NFS-e do MEI continuam a numeração das notas 1 a 8, em ordem de data, depois de 26/08/2026.
# (arquivo, data, valor, cliente, código de tributação, descrição) — mesmo formato de VENDAS
VENDAS_EXTRA = [
    ("13_venda_nfse.png", "2026-08-31", 1850.00, "I", "01.08.01", "Criação de loja virtual com catálogo de produtos e agendamento de banho e tosa."),
    ("14_venda_nfse.jpg", "2026-09-03", 2400.00, "K", "01.01.01", "Desenvolvimento de sistema de controle de matrículas e frequência de alunos."),
    ("15_venda_nfse.pdf", "2026-09-08", 980.00, "L", "01.07.01", "Instalação e configuração de sistema de frente de caixa e impressora fiscal."),
    ("16_venda_nfse.txt", "2026-09-11", 3650.00, "J", "01.01.01", "Desenvolvimento de módulo de orçamento de obras com cálculo de materiais."),
    ("17_venda_nfse.png", "2026-09-16", 1200.00, "N", "01.08.01", "Atualização do site institucional e cadastro da coleção primavera/verão."),
    ("18_venda_nfse.jpg", "2026-09-21", 2275.50, "M", "01.06.01", "Consultoria para migração de arquivos de clientes para armazenamento em nuvem."),
    ("19_venda_nfse.pdf", "2026-09-24", 4890.00, "O", "01.01.01", "Desenvolvimento de portal de anúncios de imóveis com busca por mapa."),
    ("20_venda_nfse.txt", "2026-09-29", 1575.00, "P", "01.07.01", "Manutenção preventiva de servidores e rotina de backup - competência 09/2026."),
    ("21_venda_nfse.png", "2026-10-02", 850.00, "I", "01.07.01", "Suporte técnico mensal - competência 09/2026."),
    ("22_venda_nfse.jpg", "2026-10-07", 3120.00, "K", "01.02.01", "Programação de aplicativo de treinos personalizados (Android)."),
    ("23_venda_nfse.pdf", "2026-10-13", 1990.00, "L", "01.08.01", "Criação de cardápio digital com QR Code por mesa e pedidos online."),
    ("24_venda_nfse.txt", "2026-10-16", 2780.00, "J", "01.06.01", "Assessoria na escolha e implantação de software de gestão de obras."),
    ("25_venda_nfse.png", "2026-10-21", 1340.00, "N", "01.07.01", "Configuração de rede Wi-Fi e câmeras IP na loja."),
    ("26_venda_nfse.jpg", "2026-10-26", 2050.00, "M", "01.01.01", "Desenvolvimento de integração entre planilhas de clientes e sistema contábil."),
    ("27_venda_nfse.pdf", "2026-10-29", 1680.00, "O", "01.07.01", "Suporte técnico e licenciamento de estações - competência 10/2026."),
    ("28_venda_nfse.txt", "2026-11-03", 3460.00, "P", "01.01.01", "Desenvolvimento de painel de liberação de laudos para pacientes."),
    ("29_venda_nfse.png", "2026-11-05", 760.00, "I", "01.07.01", "Recuperação de dados de disco rígido danificado."),
    ("30_venda_nfse.jpg", "2026-11-09", 2215.00, "K", "01.06.01", "Consultoria em adequação à LGPD do cadastro de alunos."),
    ("31_venda_nfse.pdf", "2026-11-11", 1430.00, "N", "01.08.01", "Campanha de páginas promocionais para a Black Friday."),
    ("32_venda_nfse.txt", "2026-11-13", 2960.00, "L", "01.02.01", "Programação de sistema de delivery próprio integrado ao cardápio digital."),
]

# ---------------------------------------------------------------------------
# Compras de mercadoria — NF-e modelo 55
# ---------------------------------------------------------------------------


def item(cod, desc, ncm, qtd, unit):
    return {"cod": cod, "desc": desc, "ncm": ncm, "cfop": "5102", "qtd": qtd, "unit": unit}


COMPRAS_NFE_EXTRA = [
    ("33_compra_nfe.pdf", 22871, "2026-01-19", "09:15:40", "Q", True, [
        item("NB-I5-16", "NOTEBOOK 14 POL CORE I5 16GB SSD 512GB", "84713012", 1, 3899.00)]),
    ("34_compra_nfe.png", 3412, "2026-02-10", "16:22:05", "V", False, [
        item("TONER-85A", "CARTUCHO DE TONER COMPATIVEL 85A", "84439933", 3, 89.90),
        item("PEN-64", "PEN DRIVE USB 3.0 64GB", "84715010", 4, 42.50)]),
    ("35_compra_nfe.jpg", 18977, "2026-03-17", "11:03:58", "E", True, [
        item("MON-24", "MONITOR LED 24 POL FULL HD IPS", "85285200", 2, 749.00),
        item("CB-HDMI", "CABO HDMI 2.0 2 METROS", "85444200", 2, 29.90)]),
    ("36_compra_nfe.pdf", 1188, "2026-04-06", "14:47:12", "X", False, [
        item("NB-ESTAB", "NOBREAK 1200VA BIVOLT", "85044040", 1, 689.00)]),
    ("37_compra_nfe.jpg", 22990, "2026-05-04", "10:20:31", "Q", True, [
        item("TEC-MEC", "TECLADO MECANICO ABNT2 SWITCH MARROM", "84716052", 1, 329.00),
        item("MOU-SF", "MOUSE SEM FIO ERGONOMICO VERTICAL", "84716053", 1, 189.00),
        item("HDST-01", "HEADSET USB COM CANCELAMENTO DE RUIDO", "85183000", 1, 279.00)]),
    ("38_compra_nfe.png", 3355, "2026-06-15", "15:55:09", "F", False, [
        item("MESA-REG", "MESA COM REGULAGEM DE ALTURA ELETRICA 120X60", "94033000", 1, 1890.00)]),
    ("39_compra_nfe.pdf", 19340, "2026-07-21", "09:41:26", "E", True, [
        item("RTR-AX", "ROTEADOR WI-FI 6 AX3000 DUAL BAND", "85176241", 1, 549.00),
        item("SW-8P", "SWITCH GIGABIT 8 PORTAS", "85176239", 1, 219.00)]),
    ("40_compra_nfe.png", 3611, "2026-08-19", "13:12:44", "V", False, [
        item("RESMA-A4", "RESMA PAPEL A4 75G 500FL", "48025610", 5, 31.50),
        item("ORG-ARQ", "ARQUIVO MORTO PLASTICO", "39261000", 10, 7.90)]),
    ("41_compra_nfe.png", 23315, "2026-10-13", "17:28:03", "Q", True, [
        item("HD-EXT2", "HD EXTERNO 2TB USB 3.0", "84717012", 2, 459.00)]),
]

# ---------------------------------------------------------------------------
# Compras de serviço — NFS-e com o MEI como tomador
# (número, arquivo, data, valor, prestador, CTN, descrição)
# ---------------------------------------------------------------------------

COMPRAS_NFSE_EXTRA = [
    (5521, "42_compra_nfse.pdf", "2026-01-31", 149.90, "R", "01.07.01", "Plano de internet fibra empresarial 500 Mbps - competência 01/2026."),
    (887, "43_compra_nfse.txt", "2026-03-31", 89.00, "S", "01.03.01", "Hospedagem de sites e servidor de e-mail - plano anual, parcela 03/12."),
    (1452, "44_compra_nfse.png", "2026-05-20", 180.00, "T", "17.19.01", "Assessoria contábil para MEI: DAS, DASN-SIMEI e orientações - 05/2026."),
    (310, "45_compra_nfse.jpg", "2026-07-08", 497.00, "U", "08.02.01", "Curso livre online de arquitetura de software em nuvem (40 horas)."),
    (2408, "46_compra_nfse.pdf", "2026-10-12", 612.40, "G", "03.03.01", "Mensalidade de estação de trabalho compartilhada (coworking) - competência 10/2026."),
]

# ---------------------------------------------------------------------------
# Compras no varejo — NFC-e modelo 65 (cupom)
# (arquivo, número, data, hora, fornecedor, itens, desconto, foto?)
# ---------------------------------------------------------------------------


def cupom(cod, desc, qtd, unit):
    return {"cod": cod, "desc": desc, "qtd": qtd, "unit": unit}


COMPRAS_NFCE_EXTRA = [
    ("47_compra_nfce_foto.jpg", 10233, "2026-02-26", "18:05:44", "W", [
        cupom("0101", "CAFE TORRADO MOIDO 500G", 2, 24.90),
        cupom("0102", "ACUCAR REFINADO 1KG", 1, 5.49),
        cupom("0103", "COPO DESCARTAVEL 200ML C/100", 3, 7.80)], 0.00),
    ("48_compra_nfce_foto.jpg", 5590, "2026-04-18", "11:47:20", "Y", [
        cupom("0201", "ADESIVO VINIL RECORTE LOGOMARCA", 20, 4.50),
        cupom("0202", "FOLDER A5 COUCHE 4X4 500UN", 1, 265.00)], 25.00),
    ("49_compra_nfce_foto.jpg", 77412, "2026-06-09", "19:22:16", "X", [
        cupom("0301", "FILTRO DE LINHA 6 TOMADAS", 2, 39.90),
        cupom("0302", "LAMPADA LED 12W BIVOLT", 4, 11.90),
        cupom("0303", "EXTENSAO ELETRICA 5M", 1, 34.90)], 10.00),
    ("50_compra_nfce_foto.jpg", 6114, "2026-08-05", "10:09:33", "V", [
        cupom("0401", "CADERNO UNIVERSITARIO 200FL", 2, 26.90),
        cupom("0402", "CANETA ESFEROGRAFICA AZUL C/10", 1, 18.50),
        cupom("0403", "POST-IT 76X76 C/4 BLOCOS", 2, 21.90)], 0.00),
    ("51_compra_nfce_foto.jpg", 10987, "2026-09-17", "17:31:02", "W", [
        cupom("0501", "AGUA MINERAL 1,5L FARDO C/6", 2, 15.90),
        cupom("0502", "BISCOITO CREAM CRACKER 400G", 3, 6.49)], 0.00),
    ("52_compra_nfce_foto.jpg", 6402, "2026-11-10", "15:58:47", "Y", [
        cupom("0601", "IMPRESSAO COLORIDA A4 LASER", 150, 1.20),
        cupom("0602", "ENCADERNACAO ESPIRAL ATE 100FL", 6, 8.00)], 15.00),
]


# ---------------------------------------------------------------------------
# Tela de desenho em milímetros, renderizada em PNG/JPG (Pillow) e PDF vetorial
# ---------------------------------------------------------------------------

_FONTE_CACHE: dict = {}


def _fonte(negrito: bool, px: int):
    chave = (negrito, px)
    if chave not in _FONTE_CACHE:
        _FONTE_CACHE[chave] = ImageFont.truetype(str(FONTES / ("arialbd.ttf" if negrito else "arial.ttf")), px)
    return _FONTE_CACHE[chave]


def largura_mm(texto: str, pt: float, negrito: bool = False) -> float:
    return _fonte(negrito, 100).getlength(texto) * pt / 100 * 25.4 / 72


def quebrar(texto: str, pt: float, largura: float, negrito: bool = False) -> list[str]:
    linhas, atual = [], ""
    for palavra in texto.split():
        tentativa = f"{atual} {palavra}".strip()
        if largura_mm(tentativa, pt, negrito) <= largura or not atual:
            atual = tentativa
        else:
            linhas.append(atual)
            atual = palavra
    return linhas + ([atual] if atual else [])


class Tela:
    def __init__(self, largura: float, altura: float):
        self.w, self.h, self.ops = largura, altura, []

    def caixa(self, x, y, w, h, espessura=0.25):
        self.ops.append(("caixa", x, y, w, h, espessura))

    def preencher(self, x, y, w, h, cinza=0.0):
        self.ops.append(("preencher", x, y, w, h, cinza))

    def linha(self, x1, y1, x2, y2, espessura=0.25):
        self.ops.append(("linha", x1, y1, x2, y2, espessura))

    def texto(self, x, y, txt, pt=8, negrito=False, alinhar="e"):
        """`y` é a linha de base; `alinhar` em e(squerda), c(entro) ou d(ireita)."""
        self.ops.append(("texto", x, y, str(txt), pt, negrito, alinhar))

    def paragrafo(self, x, y, largura, txt, pt=7, negrito=False, entrelinha=1.25) -> float:
        for linha in quebrar(txt, pt, largura, negrito):
            y += pt * 0.3528 * entrelinha
            self.texto(x, y, linha, pt, negrito)
        return y

    def marca_dagua(self, txt, pt=40):
        self.ops.append(("marca", txt, pt))

    def campo(self, x, y, w, h, rotulo, valor="", pt=8, negrito=False, alinhar="e"):
        """Quadro do DANFE: rótulo pequeno em cima, conteúdo embaixo."""
        self.caixa(x, y, w, h)
        self.texto(x + 0.8, y + 2.2, rotulo.upper(), 5)
        if valor != "":
            xv = {"e": x + 0.8, "c": x + w / 2, "d": x + w - 0.8}[alinhar]
            self.texto(xv, y + h - 1.3, valor, pt, negrito, alinhar)

    def codigo_barras(self, x, y, w, h, digitos: str):
        modulos = code128c(digitos)
        passo = w / len(modulos)
        for i, bit in enumerate(modulos):
            if bit == "1":
                self.preencher(x + i * passo, y, passo * 1.02, h)

    def qr(self, x, y, lado, conteudo: str):
        qr = qrcode.QRCode(border=0, error_correction=qrcode.constants.ERROR_CORRECT_M)
        qr.add_data(conteudo)
        matriz = qr.get_matrix()
        passo = lado / len(matriz)
        for i, linha in enumerate(matriz):
            for j, cheio in enumerate(linha):
                if cheio:
                    self.preencher(x + j * passo, y + i * passo, passo * 1.02, passo * 1.02)

    # -- renderização ------------------------------------------------------

    def png(self, dpi=150) -> Image.Image:
        s = dpi / 25.4
        img = Image.new("RGB", (round(self.w * s), round(self.h * s)), "white")
        d = ImageDraw.Draw(img)
        for op in self.ops:
            if op[0] == "marca":
                _, txt, pt = op
                fonte = _fonte(True, round(pt * dpi / 72))
                camada = Image.new("L", (round(fonte.getlength(txt)) + 20, round(pt * dpi / 72 * 1.4)), 0)
                ImageDraw.Draw(camada).text((10, 0), txt, fill=255, font=fonte)
                camada = camada.rotate(35, expand=True, resample=Image.BICUBIC)
                cinza = Image.new("RGB", camada.size, (205, 205, 205))
                img.paste(cinza, ((img.width - camada.width) // 2, (img.height - camada.height) // 2), camada)
        for op in self.ops:
            tipo = op[0]
            if tipo == "caixa":
                _, x, y, w, h, e = op
                d.rectangle([x * s, y * s, (x + w) * s, (y + h) * s], outline="black", width=max(1, round(e * s)))
            elif tipo == "preencher":
                _, x, y, w, h, c = op
                tom = round(255 * c)
                d.rectangle([x * s, y * s, (x + w) * s, (y + h) * s], fill=(tom, tom, tom))
            elif tipo == "linha":
                _, x1, y1, x2, y2, e = op
                d.line([x1 * s, y1 * s, x2 * s, y2 * s], fill="black", width=max(1, round(e * s)))
            elif tipo == "texto":
                _, x, y, txt, pt, negrito, alinhar = op
                ancora = {"e": "ls", "c": "ms", "d": "rs"}[alinhar]
                d.text((x * s, y * s), txt, fill="black", font=_fonte(negrito, round(pt * dpi / 72)), anchor=ancora)
        return img

    def pdf(self) -> bytes:
        k = 72 / 25.4
        H = self.h

        def esc(t):
            return t.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

        ops = []
        for op in self.ops:
            if op[0] == "marca":
                _, txt, pt = op
                larg = largura_mm(txt, pt, True)
                import math
                a, b = math.cos(math.radians(35)), math.sin(math.radians(35))
                cx, cy = self.w / 2 - a * larg / 2, H / 2 - b * larg / 2
                ops.append(f"BT 0.8 g /F2 {pt} Tf {a:.4f} {b:.4f} {-b:.4f} {a:.4f} {cx * k:.2f} {cy * k:.2f} Tm ({esc(txt)}) Tj ET 0 g")
        for op in self.ops:
            tipo = op[0]
            if tipo == "caixa":
                _, x, y, w, h, e = op
                ops.append(f"{e * k:.2f} w {x * k:.2f} {(H - y - h) * k:.2f} {w * k:.2f} {h * k:.2f} re S")
            elif tipo == "preencher":
                _, x, y, w, h, c = op
                ops.append(f"{c} g {x * k:.2f} {(H - y - h) * k:.2f} {w * k:.2f} {h * k:.2f} re f 0 g")
            elif tipo == "linha":
                _, x1, y1, x2, y2, e = op
                ops.append(f"{e * k:.2f} w {x1 * k:.2f} {(H - y1) * k:.2f} m {x2 * k:.2f} {(H - y2) * k:.2f} l S")
            elif tipo == "texto":
                _, x, y, txt, pt, negrito, alinhar = op
                deslocamento = {"e": 0, "c": largura_mm(txt, pt, negrito) / 2, "d": largura_mm(txt, pt, negrito)}[alinhar]
                fonte = "/F2" if negrito else "/F1"
                ops.append(f"BT {fonte} {pt} Tf {(x - deslocamento) * k:.2f} {(H - y) * k:.2f} Td ({esc(txt)}) Tj ET")
        conteudo = "\n".join(ops).encode("cp1252")
        objs = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %.2f %.2f] /Contents 4 0 R "
            b"/Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> >>" % (self.w * k, self.h * k),
            b"<< /Length %d >>\nstream\n" % len(conteudo) + conteudo + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
        ]
        saida, offsets = bytearray(b"%PDF-1.4\n"), []
        for i, obj in enumerate(objs, 1):
            offsets.append(len(saida))
            saida += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
        xref = len(saida)
        saida += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
        saida += b"".join(b"%010d 00000 n \n" % o for o in offsets)
        saida += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
        return bytes(saida)


# Code 128 (larguras barra/espaço de cada símbolo); a chave usa o conjunto C.
_C128 = ("212222 222122 222221 121223 121322 131222 122213 122312 132212 221213 221312 231212 112232 "
         "122132 122231 113222 123122 123221 223211 221132 221231 213212 223112 312131 311222 321122 "
         "321221 312212 322112 322211 212123 212321 232121 111323 131123 131321 112313 132113 132311 "
         "211313 231113 231311 112133 112331 132131 113123 113321 133121 313121 211331 231131 213113 "
         "213311 213131 311123 311321 331121 312113 312311 332111 314111 221411 431111 111224 111422 "
         "121124 121421 141122 141221 112214 112412 122114 122411 142112 142211 241211 221114 413111 "
         "241112 134111 111242 121142 121241 114212 124112 124211 411212 421112 421211 212141 214121 "
         "412121 111143 111341 131141 114113 114311 411113 411311 113141 114131 311141 411131 211412 "
         "211214 211232 2331112").split()
assert len(_C128) == 107 and all(sum(map(int, p)) == 11 for p in _C128[:106])


def code128c(digitos: str) -> str:
    valores = [105] + [int(digitos[i:i + 2]) for i in range(0, len(digitos), 2)]
    valores.append((valores[0] + sum(v * i for i, v in enumerate(valores[1:], 1))) % 103)
    valores.append(106)
    bits = "0" * 10
    for v in valores:
        for i, largura in enumerate(_C128[v]):
            bits += ("1" if i % 2 == 0 else "0") * int(largura)
    return bits + "0" * 10


# ---------------------------------------------------------------------------
# DANFSe — padrão nacional (NFS-e Nacional, leiaute v1.0)
# ---------------------------------------------------------------------------


def secoes_nfse(numero, data, valor, prest, tom, ctn, descricao, eh_mei):
    regime_sn = ("Optante - Microempreendedor Individual (MEI)" if eh_mei
                 else "Optante - Microempresa ou Empresa de Pequeno Porte (ME/EPP)")
    apuracao = "-" if eh_mei else "Regime de apuração dos tributos federais e municipal pelo SN"
    municipio = f"{SAO_PAULO[0]} - {SAO_PAULO[1]}"
    info = ("Prestador optante pelo SIMEI. ISSQN e tributos federais recolhidos mensalmente em valor "
            "fixo no DAS-MEI (LC 123/2006, art. 18-A). Não há retenção na fonte." if eh_mei else
            "Documento emitido por ME/EPP optante pelo Simples Nacional. ISSQN apurado no DAS.")
    aliquota = "-" if eh_mei else "2,00%"
    issqn = "-" if eh_mei else brl(valor * 0.02)
    hora = f"{9 + numero % 8:02d}:{(numero * 7) % 60:02d}:{(numero * 13) % 60:02d}"
    return [
        (None, [[("Número da NFS-e", str(numero), 1), ("Competência da NFS-e", data_br(data), 1),
                 ("Data e Hora da emissão da NFS-e", f"{data_br(data)} {hora}", 1)],
                [("Número da DPS", str(numero), 1), ("Série da DPS", "900", 1),
                 ("Data e Hora da emissão da DPS", f"{data_br(data)} {hora}", 1)]]),
        ("EMITENTE DA NFS-e  -  Prestador do Serviço",
         [[("CNPJ / CPF / NIF", prest["cnpj"], 1), ("Inscrição Municipal", prest.get("im") or "-", 1),
           ("Telefone", prest["fone"], 1)],
          [("Nome / Nome Empresarial", prest["nome"], 2), ("E-mail", prest.get("email") or "-", 1)],
          [("Endereço", f"{prest['end']}, {prest['bairro']}", 2), ("Município", municipio, 0.6), ("CEP", prest["cep"], 0.4)],
          [("Simples Nacional na Data de Competência", regime_sn, 1.5),
           ("Regime de Apuração Tributária pelo SN", apuracao, 1.5)]]),
        ("TOMADOR DO SERVIÇO",
         [[("CNPJ / CPF / NIF", tom["cnpj"], 1), ("Inscrição Municipal", tom.get("im") or "-", 1),
           ("Telefone", tom["fone"], 1)],
          [("Nome / Nome Empresarial", tom["nome"], 2), ("E-mail", tom.get("email") or "-", 1)],
          [("Endereço", f"{tom['end']}, {tom['bairro']}", 2), ("Município", municipio, 0.6), ("CEP", tom["cep"], 0.4)]]),
        ("INTERMEDIÁRIO DO SERVIÇO", [[("", "NÃO IDENTIFICADO NA NFS-e", 1)]]),
        ("SERVIÇO PRESTADO",
         [[("Código de Tributação Nacional", f"{ctn} - {CTN[ctn]}", 3)],
          [("Código de Tributação Municipal", ctn.replace(".", "")[:4] + "0", 1),
           ("Local da Prestação", municipio, 1), ("País da Prestação", "Brasil", 1)],
          [("Descrição do Serviço", descricao, 3)]]),
        ("TRIBUTAÇÃO MUNICIPAL",
         [[("Tributação do ISSQN", "Operação Tributável", 1), ("País Resultado da Prestação do Serviço", "-", 1),
           ("Município de Incidência do ISSQN", municipio, 1), ("Regime Especial de Tributação", "Nenhum", 1)],
          [("Valor do Serviço", brl(valor), 1), ("Desconto Incondicionado", "-", 1),
           ("Total Deduções/Reduções", "-", 1), ("Cálculo do BM", "-", 1)],
          [("BC ISSQN", "-" if eh_mei else brl(valor), 1), ("Alíquota Aplicada", aliquota, 1),
           ("Retenção do ISSQN", "Não Retido", 1), ("ISSQN Apurado", issqn, 1)]]),
        ("TRIBUTAÇÃO FEDERAL",
         [[("IRRF", "-", 1), ("Contribuição Previdenciária - Retida", "-", 1), ("CSLL", "-", 1),
           ("PIS", "-", 1), ("COFINS", "-", 1)]]),
        ("VALOR TOTAL DA NFS-E",
         [[("Valor do Serviço", brl(valor), 1), ("Desconto Condicionado", "R$ 0,00", 1),
           ("Desconto Incondicionado", "R$ 0,00", 1), ("ISSQN Retido", "-", 1)],
          [("IRRF, CP, CSLL - Retidos", "R$ 0,00", 1), ("PIS/COFINS Retidos", "-", 1),
           ("Valor Líquido da NFS-e", brl(valor), 2)]]),
        ("TOTAIS APROXIMADOS DOS TRIBUTOS",
         [[("Federais", "-", 1), ("Estaduais", "-", 1), ("Municipais", "-", 1)]]),
        ("INFORMAÇÕES COMPLEMENTARES", [[("", info, 1)]]),
    ]


def danfse(chave, secoes) -> Tela:
    t = Tela(210, 297)
    m, L = 8, 194
    t.marca_dagua("SEM VALOR FISCAL", 64)
    t.caixa(m, m, L, 22, 0.4)
    t.texto(m + 3, m + 8, "NFS-e", 18, True)
    t.texto(m + 3, m + 13, "Nota Fiscal de Serviço eletrônica", 7)
    t.texto(m + L / 2 - 8, m + 7, "DANFSe v1.0", 11, True, "c")
    t.texto(m + L / 2 - 8, m + 11.5, "Documento Auxiliar da NFS-e", 8, False, "c")
    t.texto(m + L / 2 - 8, m + 16, "Prefeitura do Município de São Paulo", 7, False, "c")
    t.texto(m + L / 2 - 8, m + 20, HOMOLOGACAO.replace("HOMOLOGAÇÃO", "PRODUÇÃO RESTRITA"), 6, True, "c")
    t.qr(m + L - 20, m + 1.5, 19, f"https://www.nfse.gov.br/ConsultaPublica/?tpc=1&chave={chave}")
    y = m + 22
    t.campo(m, y, L, 8, "Chave de Acesso da NFS-e", agrupar(chave), 9, True)
    y += 8
    for titulo, linhas in secoes:
        if titulo:
            t.preencher(m, y, L, 4.5, 0.88)
            t.caixa(m, y, L, 4.5)
            t.texto(m + 1.5, y + 3.3, titulo, 7, True)
            y += 4.5
        for linha in linhas:
            total = sum(p for _, _, p in linha)
            alturas = [len(quebrar(v, 7.5, L * p / total - 2)) for _, v, p in linha]
            h = 4 + 3.4 * max(alturas)
            x = m
            for rotulo, valor, peso in linha:
                w = L * peso / total
                t.caixa(x, y, w, h)
                if rotulo:
                    t.texto(x + 0.8, y + 2.4, rotulo, 5.5)
                t.paragrafo(x + 0.8, y + (2.2 if rotulo else 0.6), w - 2, valor, 7.5, entrelinha=1.25)
                x += w
            y += h
    return t


def texto_nfse(chave, secoes) -> str:
    """Versão em texto do DANFSe (como o conteúdo copiado do documento)."""
    s = ["DANFSe v1.0 - Documento Auxiliar da NFS-e", "NFS-e Nacional - Prefeitura do Município de São Paulo",
         HOMOLOGACAO.replace("HOMOLOGAÇÃO", "PRODUÇÃO RESTRITA"), "",
         f"Chave de Acesso da NFS-e: {chave}"]
    for titulo, linhas in secoes:
        s.append("")
        if titulo:
            s += [titulo, "-" * len(titulo)]
        for linha in linhas:
            for rotulo, valor, _ in linha:
                s.append(f"{rotulo}: {valor}" if rotulo else valor)
    return "\n".join(s) + "\n"


# ---------------------------------------------------------------------------
# DANFE NF-e modelo 55 — retrato (Anexo II do MOC)
# ---------------------------------------------------------------------------


def danfe(nf) -> Tela:
    t = Tela(210, 297)
    m, L = 7, 196
    emit, dest = nf["emit"], nf["dest"]
    num = f"{nf['numero']:09d}"
    num_fmt = f"{num[:3]}.{num[3:6]}.{num[6:]}"
    t.marca_dagua("SEM VALOR FISCAL", 64)

    # Canhoto
    t.caixa(m, m, L - 32, 9)
    t.paragrafo(m + 1, m + 0.3, L - 34,
                f"RECEBEMOS DE {emit['nome'].upper()} OS PRODUTOS E/OU SERVIÇOS CONSTANTES DA NOTA FISCAL "
                f"ELETRÔNICA INDICADA AO LADO. EMISSÃO: {data_br(nf['data'])}  VALOR TOTAL: {brl(nf['total'])}  "
                f"DESTINATÁRIO: {DEST_HOMOLOGACAO}", 6)
    t.campo(m, m + 9, 40, 9, "Data de recebimento")
    t.campo(m + 40, m + 9, L - 72, 9, "Identificação e assinatura do recebedor")
    t.caixa(m + L - 32, m, 32, 18)
    t.texto(m + L - 16, m + 5.5, "NF-e", 11, True, "c")
    t.texto(m + L - 16, m + 10.5, f"Nº {num_fmt}", 8, True, "c")
    t.texto(m + L - 16, m + 14.5, f"SÉRIE {nf['serie']:03d}", 8, True, "c")
    for x in range(m, m + L, 3):
        t.linha(x, m + 20, x + 1.5, m + 20)

    # Cabeçalho: emitente | DANFE | código de barras e chave
    y = m + 22
    t.caixa(m, y, 78, 34)
    t.texto(m + 39, y + 6, "IDENTIFICAÇÃO DO EMITENTE", 5, False, "c")
    yy = t.paragrafo(m + 2, y + 7, 74, emit["nome"].upper(), 9.5, True)
    for txt in (emit["end"], f"{emit['bairro']} - {emit['cep']}", "São Paulo - SP", f"Fone: {emit['fone']}"):
        yy += 3.4
        t.texto(m + 2, yy, txt, 7)
    t.caixa(m + 78, y, 34, 34)
    t.texto(m + 95, y + 6, "DANFE", 12, True, "c")
    t.paragrafo(m + 80, y + 7, 30, "Documento Auxiliar da Nota Fiscal Eletrônica", 6.5)
    t.texto(m + 80, y + 18, "0 - ENTRADA", 7)
    t.texto(m + 80, y + 21.5, "1 - SAÍDA", 7)
    t.caixa(m + 101, y + 15.5, 6, 6.5)
    t.texto(m + 104, y + 20.5, "1", 10, True, "c")
    t.texto(m + 95, y + 26, f"Nº {num_fmt}", 7.5, True, "c")
    t.texto(m + 95, y + 29.5, f"SÉRIE {nf['serie']:03d}", 7.5, True, "c")
    t.texto(m + 95, y + 33, "FOLHA 1/1", 7, False, "c")
    xr, wr = m + 112, L - 112
    t.caixa(xr, y, wr, 13)
    t.codigo_barras(xr + 3, y + 1.5, wr - 6, 10, nf["chave"])
    t.campo(xr, y + 13, wr, 8, "Chave de acesso", agrupar(nf["chave"]), 8, True, "c")
    t.caixa(xr, y + 21, wr, 13)
    t.paragrafo(xr + 1, y + 21.5, wr - 2, "Consulta de autenticidade no portal nacional da NF-e "
                "www.nfe.fazenda.gov.br/portal ou no site da Sefaz Autorizadora", 7.5)

    y += 34
    t.campo(m, y, 112, 8, "Natureza da operação", nf["natureza"])
    t.campo(m + 112, y, L - 112, 8, "Protocolo de autorização de uso",
            f"{nf['protocolo']} - {data_br(nf['data'])} {nf['hora']}", 8, False, "c")
    y += 8
    t.campo(m, y, 65, 8, "Inscrição estadual", emit["ie"])
    t.campo(m + 65, y, 65, 8, "Insc. estadual do subst. trib.")
    t.campo(m + 130, y, L - 130, 8, "CNPJ", emit["cnpj"])

    def titulo(yt, txt):
        t.texto(m, yt + 2.8, txt, 6.5, True)
        return yt + 3.5

    y = titulo(y + 9, "DESTINATÁRIO / REMETENTE")
    t.campo(m, y, 118, 8, "Nome / Razão social", DEST_HOMOLOGACAO, 7.5)
    t.campo(m + 118, y, 46, 8, "CNPJ / CPF", dest["cnpj"], 8, False, "c")
    t.campo(m + 164, y, L - 164, 8, "Data da emissão", data_br(nf["data"]), 8, False, "c")
    y += 8
    t.campo(m, y, 90, 8, "Endereço", dest["end"])
    t.campo(m + 90, y, 46, 8, "Bairro / Distrito", dest["bairro"])
    t.campo(m + 136, y, 28, 8, "CEP", dest["cep"], 8, False, "c")
    t.campo(m + 164, y, L - 164, 8, "Data da saída/entrada", data_br(nf["data"]), 8, False, "c")
    y += 8
    t.campo(m, y, 70, 8, "Município", "São Paulo")
    t.campo(m + 70, y, 36, 8, "Fone / Fax", dest["fone"])
    t.campo(m + 106, y, 12, 8, "UF", "SP", 8, False, "c")
    t.campo(m + 118, y, 46, 8, "Inscrição estadual", "ISENTO", 8, False, "c")
    t.campo(m + 164, y, L - 164, 8, "Hora da saída/entrada", nf["hora"], 8, False, "c")

    y = titulo(y + 9, "CÁLCULO DO IMPOSTO")
    bc, icms = nf["bc_icms"], nf["v_icms"]
    w6 = L / 6
    for i, (r, v) in enumerate([("Base de cálc. do ICMS", bc), ("Valor do ICMS", icms), ("Base de cálc. ICMS S.T.", 0),
                                ("Valor do ICMS subst.", 0), ("V. aprox. tributos", nf["tributos"]),
                                ("V. total produtos", nf["produtos"])]):
        t.campo(m + i * w6, y, w6, 8, r, brl(v, False), 8, False, "d")
    y += 8
    for i, (r, v) in enumerate([("Valor do frete", 0), ("Valor do seguro", 0), ("Desconto", nf["desconto"]),
                                ("Outras desp. acess.", 0), ("Valor do IPI", 0), ("V. total da nota", nf["total"])]):
        t.campo(m + i * w6, y, w6, 8, r, brl(v, False), 8, i == 5, "d")

    y = titulo(y + 9, "TRANSPORTADOR / VOLUMES TRANSPORTADOS")
    t.campo(m, y, 70, 8, "Nome / Razão social")
    t.campo(m + 70, y, 40, 8, "Frete por conta", "9-Sem Ocorrência de Transporte", 6.5)
    t.campo(m + 110, y, 22, 8, "Código ANTT")
    t.campo(m + 132, y, 22, 8, "Placa do veículo")
    t.campo(m + 154, y, 10, 8, "UF")
    t.campo(m + 164, y, L - 164, 8, "CNPJ / CPF")

    y = titulo(y + 9, "DADOS DOS PRODUTOS / SERVIÇOS")
    colunas = [("CÓDIGO", 14, "e"), ("DESCRIÇÃO DO PRODUTO / SERVIÇO", 50, "e"), ("NCM/SH", 14, "c"),
               ("CST/CSOSN", 11, "c"), ("CFOP", 9, "c"), ("UN", 8, "c"), ("QUANT", 12, "d"),
               ("V. UNITÁRIO", 16, "d"), ("V. TOTAL", 16, "d"), ("BC ICMS", 14, "d"), ("V. ICMS", 12, "d"),
               ("ALÍQ. ICMS", 10, "d"), ("V. IPI", 10, "d")]
    altura_tabela = 297 - m - 32 - y
    t.caixa(m, y, L, altura_tabela)
    t.linha(m, y + 5, m + L, y + 5)
    x = m
    for rotulo, w, _ in colunas:
        t.texto(x + w / 2, y + 3.3, rotulo, 5, True, "c")
        t.linha(x + w, y, x + w, y + altura_tabela)
        x += w
    yl = y + 5
    for item in nf["itens"]:
        valores = [item["cod"], item["desc"], item["ncm"], item["csosn"], item["cfop"], "UN",
                   f"{item['qtd']:.4f}".replace(".", ","), brl(item["unit"], False),
                   brl(item["qtd"] * item["unit"], False), brl(item["bc"], False), brl(item["icms"], False),
                   item["aliq"], "0,00"]
        x = m
        linhas_desc = quebrar(item["desc"], 6.5, 48)
        for (rotulo, w, alinhar), v in zip(colunas, valores):
            if rotulo.startswith("DESCRIÇÃO"):
                yy = yl
                for linha in linhas_desc:
                    yy += 2.9
                    t.texto(x + 1, yy, linha, 6.5)
            else:
                xv = {"e": x + 1, "c": x + w / 2, "d": x + w - 1}[alinhar]
                t.texto(xv, yl + 2.9, v, 6.5, False, alinhar)
            x += w
        yl += 2.9 * len(linhas_desc) + 1.5

    y = titulo(297 - m - 32 + 0.5, "DADOS ADICIONAIS")
    t.caixa(m, y, 130, 28)
    t.texto(m + 0.8, y + 2.2, "INFORMAÇÕES COMPLEMENTARES", 5)
    t.paragrafo(m + 1, y + 2.5, 127, nf["info"], 6.5)
    t.campo(m + 130, y, L - 130, 28, "Reservado ao fisco")
    return t


def nfe_compra(arquivo, numero, data, hora, forn, itens, regime_normal):
    produtos = round(sum(i["qtd"] * i["unit"] for i in itens), 2)
    for i in itens:
        total_item = i["qtd"] * i["unit"]
        if regime_normal:
            i.update(csosn="000", bc=total_item, icms=round(total_item * 0.18, 2), aliq="18,00")
        else:
            i.update(csosn="0102", bc=0, icms=0, aliq="0,00")
    bc = round(sum(i["bc"] for i in itens), 2)
    info = (f"Inf. Contribuinte: Pedido 2026/{numero:05d}. Valor aproximado dos tributos: "
            f"{brl(produtos * 0.3184)} (31,84%) Fonte: IBPT. {HOMOLOGACAO}.")
    if not regime_normal:
        info = ("DOCUMENTO EMITIDO POR ME OU EPP OPTANTE PELO SIMPLES NACIONAL. NÃO GERA DIREITO A "
                "CRÉDITO FISCAL DE IPI. " + info)
    return {
        "arquivo": arquivo, "numero": numero, "serie": 1, "data": data, "hora": hora,
        "emit": forn, "dest": MEI, "itens": itens, "natureza": "VENDA DE MERCADORIA ADQ. DE TERCEIROS",
        "chave": chave_nfe("35", data, forn["cnpj"], "55", 1, numero),
        "protocolo": f"1352600{random.randrange(10**8):08d}", "produtos": produtos, "desconto": 0.0,
        "total": produtos, "bc_icms": bc, "v_icms": round(sum(i["icms"] for i in itens), 2),
        "tributos": round(produtos * 0.3184, 2), "info": info,
    }


# ---------------------------------------------------------------------------
# DANFE NFC-e modelo 65 (cupom 80 mm), fotografado em más condições
# ---------------------------------------------------------------------------


def danfe_nfce(nf) -> Tela:
    t = Tela(80, 200)
    m, L, y = 4, 72, 6
    emit = nf["emit"]

    def centro(txt, pt=7, negrito=False, passo=3.4):
        nonlocal y
        for linha in quebrar(txt, pt, L, negrito):
            y += passo
            t.texto(40, y, linha, pt, negrito, "c")

    def par(esq, dir_, pt=7, negrito=False):
        nonlocal y
        y += 3.4
        t.texto(m, y, esq, pt, negrito)
        t.texto(m + L, y, dir_, pt, negrito, "d")

    def regua():
        nonlocal y
        y += 2
        for x in range(m, m + L, 2):
            t.linha(x, y, x + 1, y, 0.2)
        y += 0.5

    centro(f"CNPJ: {emit['cnpj']}  {emit['nome']}", 7.5, True)
    centro(f"{emit['end']}, {emit['bairro']}, São Paulo - SP", 6.5)
    centro("Documento Auxiliar da Nota Fiscal de Consumidor Eletrônica", 6.5, True)
    regua()
    y += 3.4
    for x, rotulo, alinhar in ((m, "Código Descrição", "e"), (m + 40, "Qtde UN", "d"),
                               (m + 56, "Vl Unit", "d"), (m + L, "Vl Total", "d")):
        t.texto(x, y, rotulo, 6, True, alinhar)
    for item in nf["itens"]:
        y += 3.3
        t.texto(m, y, f"{item['cod']} {item['desc']}", 6.3)
        y += 3.1
        t.texto(m + 40, y, f"{item['qtd']} UN", 6.3, False, "d")
        t.texto(m + 56, y, brl(item["unit"], False), 6.3, False, "d")
        t.texto(m + L, y, brl(item["qtd"] * item["unit"], False), 6.3, False, "d")
    regua()
    par("Qtde. total de itens", str(len(nf["itens"])))
    par("Valor total R$", brl(nf["subtotal"], False))
    par("Desconto R$", brl(nf["desconto"], False))
    par("Valor a Pagar R$", brl(nf["total"], False), 8, True)
    par("FORMA PAGAMENTO", "VALOR PAGO R$", 6.3, True)
    par("Pagamento Instantâneo (PIX)", brl(nf["total"], False), 6.5)
    par("Troco R$", "0,00", 6.5)
    regua()
    centro("Consulte pela Chave de Acesso em", 6.3, True)
    centro("www.homologacao.nfce.fazenda.sp.gov.br/consulta", 6.3)
    centro(agrupar(nf["chave"]), 6.8, True)
    regua()
    centro(f"CONSUMIDOR - CNPJ {MEI['cnpj']}", 6.5, True)
    centro(DEST_HOMOLOGACAO, 6.3)
    centro(f"{MEI['end']}, {MEI['bairro']}, São Paulo - SP", 6.3)
    regua()
    centro(f"NFC-e nº {nf['numero']:09d} Série 001 {data_br(nf['data'])} {nf['hora']}", 6.5, True)
    centro(f"Protocolo de autorização: {nf['protocolo']}", 6.3)
    centro(f"Data de autorização: {data_br(nf['data'])} {nf['hora']}", 6.3)
    y += 2
    t.qr(40 - 15, y, 30, nf["qrcode"])
    y += 31
    centro("Tributos Totais Incidentes (Lei Federal 12.741/2012): " + brl(nf["total"] * 0.2735), 6.3)
    regua()
    centro(HOMOLOGACAO, 7, True)
    t.h = y + 6
    return t


def foto_ruim(img: Image.Image) -> Image.Image:
    """Leve rotação, papel amarelado, borrão, ruído e manchas."""
    papel = Image.new("RGB", img.size, (246, 242, 230))
    img = Image.blend(img, papel, 0.18)
    img = img.rotate(1.5, resample=Image.BICUBIC, expand=True, fillcolor=(90, 85, 80))
    img = img.filter(ImageFilter.GaussianBlur(0.8))
    px = img.load()
    for _ in range(img.width * img.height // 25):
        x, y = random.randrange(img.width), random.randrange(img.height)
        r, g, b = px[x, y]
        n = random.randint(-45, 45)
        px[x, y] = tuple(max(0, min(255, c + n)) for c in (r, g, b))
    d = ImageDraw.Draw(img)
    for _ in range(40):
        x, y, r = random.randrange(img.width), random.randrange(img.height), random.randint(1, 4)
        d.ellipse([x, y, x + r, y + r], fill=(120, 110, 100))
    return img


# ---------------------------------------------------------------------------
# Saída
# ---------------------------------------------------------------------------


def salvar(tela: Tela, arquivo: str, texto: str | None = None):
    caminho = AQUI / arquivo
    if caminho.suffix == ".pdf":
        caminho.write_bytes(tela.pdf())
    elif caminho.suffix == ".txt":
        caminho.write_text(texto, encoding="utf-8")
    elif caminho.suffix == ".jpg":
        tela.png(dpi=300).save(caminho, quality=88)
    else:
        tela.png(dpi=300).save(caminho)


def esperado(arquivo, tipo, documento, data, valor, emit, dest, chave, extra=None):
    item = {"arquivo": arquivo, "tipo": tipo, "documento": documento, "data": data, "valor_total": valor,
            "cnpj_emitente": emit, "cnpj_destinatario": dest, "chave_acesso": chave}
    return item | (extra or {})


PERGUNTAS = [
    ("Se eu faturar mais do que o teto permitido no ano, o que acontece comigo?",
     "Consequências de ultrapassar o limite anual"),
    ("Aquele boleto que pago todo mês como MEI serve pra quê?",
     "DAS: guia mensal do MEI"),
    ("Tenho que prestar contas à Receita de quanto ganhei no ano anterior?",
     "DASN-SIMEI: declaração anual obrigatória"),
    ("O dinheiro que gasto comprando material entra na conta do teto de faturamento?",
     "Apenas vendas contam para o limite anual do MEI"),
    ("Posso sair do MEI por vontade própria para virar microempresa?",
     "Pedido de desenquadramento voluntário"),
]


def main():
    for antigo in AQUI.glob("[0-9][0-9]_*"):
        antigo.unlink()
    gabarito = []

    for n, (arquivo, data, valor, cli, ctn, desc) in enumerate(VENDAS, 1):
        tom = CLIENTES[cli]
        chave = chave_nfse(SAO_PAULO[2], MEI["cnpj"], n, data)
        secoes = secoes_nfse(n, data, valor, MEI, tom, ctn, desc, eh_mei=True)
        salvar(danfse(chave, secoes), arquivo, texto_nfse(chave, secoes))
        gabarito.append(esperado(arquivo, "venda", "NFS-e Nacional (DANFSe)", data, valor,
                                 MEI["cnpj"], tom["cnpj"], chave))

    compras_nfe = [
        nfe_compra("09_compra_nfe.png", 18452, "2026-03-05", "10:42:17", FORNECEDORES["E"], [
            {"cod": "SSD1TB", "desc": "SSD NVME M.2 1TB LEITURA 3500MB/S", "ncm": "85235110", "cfop": "5102", "qtd": 1, "unit": 489.90},
            {"cod": "MEM16G", "desc": "MEMORIA DDR4 16GB 3200MHZ SODIMM", "ncm": "84733042", "cfop": "5102", "qtd": 2, "unit": 245.00},
            {"cod": "FNT650", "desc": "FONTE ATX 650W 80 PLUS BRONZE", "ncm": "85044090", "cfop": "5102", "qtd": 1, "unit": 310.00},
        ], regime_normal=True),
        nfe_compra("10_compra_nfe.pdf", 3307, "2026-06-02", "15:08:51", FORNECEDORES["F"], [
            {"cod": "CAD-ERG-01", "desc": "CADEIRA ERGONOMICA COM APOIO LOMBAR E BRACOS REGULAVEIS", "ncm": "94013010", "cfop": "5102", "qtd": 1, "unit": 349.00},
        ], regime_normal=False),
    ]
    for nf in compras_nfe:
        salvar(danfe(nf), nf["arquivo"])
        gabarito.append(esperado(nf["arquivo"], "compra", "NF-e modelo 55 (DANFE)", nf["data"], nf["total"],
                                 nf["emit"]["cnpj"], MEI["cnpj"], nf["chave"]))

    cow = FORNECEDORES["G"]
    chave = chave_nfse(SAO_PAULO[2], cow["cnpj"], 2291, "2026-09-12")
    secoes = secoes_nfse(2291, "2026-09-12", 612.40, cow, MEI, "03.03.01",
                         "Mensalidade de estação de trabalho compartilhada (coworking) - competência 09/2026.",
                         eh_mei=False)
    salvar(danfse(chave, secoes), "11_compra_nfse.txt", texto_nfse(chave, secoes))
    gabarito.append(esperado("11_compra_nfse.txt", "compra", "NFS-e Nacional (DANFSe)", "2026-09-12", 612.40,
                             cow["cnpj"], MEI["cnpj"], chave))

    pap = FORNECEDORES["H"]
    itens = [{"cod": "0001", "desc": "RESMA PAPEL A4 75G 500FL", "qtd": 10, "unit": 32.00},
             {"cod": "0002", "desc": "CARTAO DE VISITA 4X4 1000UN", "qtd": 1, "unit": 410.00},
             {"cod": "0003", "desc": "BANNER LONA 1X2M IMPRESSO", "qtd": 1, "unit": 250.00}]
    subtotal = sum(i["qtd"] * i["unit"] for i in itens)
    nfce = {"numero": 4871, "data": "2026-09-30", "hora": "14:32:10", "emit": pap, "itens": itens,
            "subtotal": subtotal, "desconto": 98.00, "total": subtotal - 98.00,
            "chave": chave_nfe("35", "2026-09-30", pap["cnpj"], "65", 1, 4871),
            "protocolo": f"1352600{random.randrange(10**8):08d}"}
    hash_csc = hashlib.sha1((nfce["chave"] + "|2|2|1|CSC-HOMOLOGACAO").encode()).hexdigest().upper()
    nfce["qrcode"] = f"https://www.homologacao.nfce.fazenda.sp.gov.br/qrcode?p={nfce['chave']}|2|2|1|{hash_csc}"
    tela = danfe_nfce(nfce)
    foto_ruim(tela.png(dpi=220)).save(AQUI / "12_compra_nfce_foto.jpg", quality=70)
    gabarito.append(esperado("12_compra_nfce_foto.jpg", "compra", "NFC-e modelo 65 (DANFE NFC-e), foto",
                             nfce["data"], round(nfce["total"], 2), pap["cnpj"], MEI["cnpj"], nfce["chave"],
                             {"observacao": f"valor total {brl(subtotal)}, desconto {brl(98.0)}: "
                                            "o valor correto é o VALOR A PAGAR"}))

    # Notas extras (13 a 52): mesmo padrão, fora do protocolo do artigo.
    for nota in gabarito:
        nota["conjunto"] = "artigo"
    extras = []
    CTN.update(CTN_EXTRA)
    clientes = CLIENTES | CLIENTES_EXTRA
    fornecedores = FORNECEDORES | FORNECEDORES_EXTRA
    for n, (arquivo, data, valor, cli, ctn, desc) in enumerate(VENDAS_EXTRA, len(VENDAS) + 1):
        tom = clientes[cli]
        chave = chave_nfse(SAO_PAULO[2], MEI["cnpj"], n, data)
        secoes = secoes_nfse(n, data, valor, MEI, tom, ctn, desc, eh_mei=True)
        salvar(danfse(chave, secoes), arquivo, texto_nfse(chave, secoes))
        extras.append(esperado(arquivo, "venda", "NFS-e Nacional (DANFSe)", data, valor,
                               MEI["cnpj"], tom["cnpj"], chave))
    for arquivo, numero, data, hora, f, regime_normal, itens in COMPRAS_NFE_EXTRA:
        nf = nfe_compra(arquivo, numero, data, hora, fornecedores[f], itens, regime_normal)
        salvar(danfe(nf), arquivo)
        extras.append(esperado(arquivo, "compra", "NF-e modelo 55 (DANFE)", data, nf["total"],
                               nf["emit"]["cnpj"], MEI["cnpj"], nf["chave"]))
    for numero, arquivo, data, valor, f, ctn, desc in COMPRAS_NFSE_EXTRA:
        prest = fornecedores[f]
        chave = chave_nfse(SAO_PAULO[2], prest["cnpj"], numero, data)
        secoes = secoes_nfse(numero, data, valor, prest, MEI, ctn, desc, eh_mei=False)
        salvar(danfse(chave, secoes), arquivo, texto_nfse(chave, secoes))
        extras.append(esperado(arquivo, "compra", "NFS-e Nacional (DANFSe)", data, valor,
                               prest["cnpj"], MEI["cnpj"], chave))
    for arquivo, numero, data, hora, f, itens, desconto in COMPRAS_NFCE_EXTRA:
        emit = fornecedores[f]
        subtotal = round(sum(i["qtd"] * i["unit"] for i in itens), 2)
        nf = {"numero": numero, "data": data, "hora": hora, "emit": emit, "itens": itens,
              "subtotal": subtotal, "desconto": desconto, "total": round(subtotal - desconto, 2),
              "chave": chave_nfe("35", data, emit["cnpj"], "65", 1, numero),
              "protocolo": f"1352600{random.randrange(10**8):08d}"}
        hash_csc = hashlib.sha1((nf["chave"] + "|2|2|1|CSC-HOMOLOGACAO").encode()).hexdigest().upper()
        nf["qrcode"] = f"https://www.homologacao.nfce.fazenda.sp.gov.br/qrcode?p={nf['chave']}|2|2|1|{hash_csc}"
        foto_ruim(danfe_nfce(nf).png(dpi=220)).save(AQUI / arquivo, quality=70)
        extra = ({"observacao": f"valor total {brl(subtotal)}, desconto {brl(desconto)}: "
                                "o valor correto é o VALOR A PAGAR"} if desconto else None)
        extras.append(esperado(arquivo, "compra", "NFC-e modelo 65 (DANFE NFC-e), foto", data, nf["total"],
                               emit["cnpj"], MEI["cnpj"], nf["chave"], extra))
    for nota in extras:
        nota["conjunto"] = "extra"
    gabarito += extras
    chaves = [n["chave_acesso"] for n in gabarito]
    assert len(set(chaves)) == len(chaves), "chave de acesso repetida"

    (AQUI / "gabarito.json").write_text(
        json.dumps({"notas": gabarito,
                    "perguntas_rag": [{"pergunta": p, "trecho_esperado": t} for p, t in PERGUNTAS]},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(gabarito)} notas ({len(gabarito) - len(extras)} do artigo + {len(extras)} extras) "
          f"e {len(PERGUNTAS)} perguntas geradas em {AQUI}")


if __name__ == "__main__":
    main()
