export type TxType = "venda" | "compra";

export type Summary = {
  email: string;
  year: number;
  total_revenue: number; // soma apenas de vendas (conta para o limite do MEI)
  total_despesas: number; // soma apenas de compras (não conta para o limite)
  saldo_liquido: number; // total_revenue - total_despesas
  annual_limit: number;
  remaining: number;
  exceeded: boolean;
  percent_used: number;
  alert_level: "ok" | "warning" | "exceeded";
  /** A partir de quantos % do teto vira "warning" (configurável, #91). */
  alert_threshold_percent?: number;
};

export type NivelRitmo = "ok" | "atencao_ritmo" | "atencao" | "risco" | "estourado" | "desenquadramento";

export type Tendencia = "acelerando" | "estavel" | "desacelerando";

// GET /limits/ritmo/{email} (US-25, sobre a US-28). `nivel` aqui tem 6
// estados — combina realizado e projetado — diferente do `alert_level` (3
// estados, só realizado) de Summary.
export type Ritmo = {
  email: string;
  year: number;
  limite_aplicavel: number;
  meses_de_atividade: number | null;
  proporcional: boolean;
  total_vendas: number;
  restante: number;
  percent_used: number;
  nivel: NivelRitmo;
  dias_decorridos: number;
  total_dias_ano: number;
  taxa_diaria: number;
  taxa_diaria_referencia: number;
  taxa_diaria_recente: number;
  taxa_diaria_90d: number;
  indice_ritmo: number | null;
  aceleracao: number | null;
  tendencia: Tendencia;
  projecao_disponivel: boolean;
  motivo_indisponivel: string | null;
  projecao_anual: number | null;
  dias_ate_estouro: number | null;
  data_prevista_estouro: string | null;
  faturamento_seguro_mes: number;
  influenciada_por_lancamento_atipico: boolean;
};

// GET /limits/ritmo/{email}/serie (US-26) — um ponto por dia, acumulado real.
export type PontoSerieAcumulada = {
  data: string; // ISO (YYYY-MM-DD)
  acumulado: number;
};

// GET /limits/mensal/{email} (US-27). Sempre 12 pontos, mês sem lançamento
// incluso com zero.
export type MesResumo = {
  mes: number; // 1 a 12
  vendas: number;
  despesas: number;
  meta: number; // limite_aplicavel / 12
  acima_da_meta: boolean;
};

// GET /limits/concentracao/{email} (US-27). Um item por CNPJ de cliente
// identificado, do maior para o menor. `nome` ainda não é preenchido por
// nenhum serviço (ver ADR-0021) — a interface usa `cnpj` como rótulo.
export type ConcentracaoCliente = {
  cnpj: string;
  nome: string | null;
  valor: number;
  percentual: number; // sobre o total identificado, não sobre o ano inteiro
  alerta: boolean; // acima de 70% (docs/dashboard-v2.md §2.5)
};

export type Transaction = {
  id: number;
  email: string;
  amount: number;
  tx_date: string;
  source?: string | null;
  tx_type: TxType;
};

export type UploadStructured = {
  value?: number | null;
  date?: string | null;
  cnpj_emitente?: string | null;
  cnpj_destinatario?: string | null;
  description?: string | null;
  confidence?: number | null;
  tx_type_sugerido?: TxType | null;
  tx_type_auto_detectado?: boolean;
};

// #93: nota já salva que parece ser a que acabou de chegar. `mesmo_arquivo`
// distingue o reenvio do mesmo arquivo de outra foto/PDF da mesma nota.
export type Repeticao = {
  documento_id: string;
  nome_original: string;
  mesmo_arquivo: boolean;
  valor: number | null;
  data: string | null;
  tx_type: TxType | null;
  enviado_em: string;
};

export type UploadResponse = {
  original_filename: string;
  stored_filename?: string;
  size_bytes: number;
  storage_path?: string;
  ocr_text?: string;
  extracted_amount?: number | null;
  extraction_method?: "gemini" | "regex";
  limits_transaction?: Transaction | null;
  structured_data?: UploadStructured;
  // US-18: no caminho assíncrono (flag `ocr-assincrono`) o /upload responde 202
  // com o id e a URL de acompanhamento; os campos de extração vêm depois.
  documento_id?: string;
  estado?: EstadoDocumento;
  acompanhamento_url?: string;
  /** Ausente com `documentos-persistidos` desligada. */
  repeticoes?: Repeticao[];
};

export type ErroDocumento = { motivo: string; permanente: boolean };

// US-18: resposta de GET /documents/documentos/{id} — o polling da tela de
// upload lê `estado` e `erro` daqui.
export type DocumentoDetalhe = {
  documento_id: string;
  estado: EstadoDocumento;
  original_filename?: string;
  size_bytes?: number;
  erro?: ErroDocumento | null;
  ocr_text?: string;
  extraction_method?: "gemini" | "regex";
  structured_data?: UploadStructured;
  criado_em?: string;
  atualizado_em?: string;
  repeticoes?: Repeticao[];
  /** #95: o que foi salvo (com correções); ausente enquanto a nota só foi lida. */
  confirmacao?: ConfirmacaoDocumento | null;
  repeticao_de?: string[];
};

export type ConfirmacaoDocumento = {
  campos: UploadStructured & { tx_type?: TxType };
  transacao_limits_id: number | null;
};

// PATCH /documents/documentos/{id} (#95): correção de uma nota já salva.
export type CorrecaoDocumentoPayload = {
  amount: number;
  tx_date: string;
  tx_type: TxType;
  cnpj_emitente?: string | null;
  cnpj_destinatario?: string | null;
  description?: string | null;
};

export type DocumentEntry = {
  id: string;
  filename: string;
  uploadedAt: string;
  sizeBytes?: number;
  storagePath?: string;
  ocrText: string;
  structured: UploadStructured;
  limitsTransaction?: Transaction | null;
  status: "pending_review" | "confirmed" | "discarded";
  /** Salva depois do aviso de nota repetida (#93). */
  repetida?: boolean;
};

// US-20: documento persistido no MongoDB (flag `documentos-persistidos`).
// Sobrevive à troca de dispositivo porque não vive no localStorage.
export type EstadoDocumento =
  | "recebido"
  | "processando"
  | "extraido"
  | "confirmado"
  | "descartado"
  | "erro";

export type DocumentoPersistido = {
  id: string;
  nome_original: string;
  tamanho_bytes: number;
  tipo_mime: string;
  estado: EstadoDocumento;
  extracao: { metodo: "gemini" | "regex"; campos: UploadStructured; confianca: number };
  // O que o usuário confirmou (com correções). Ausente/nulo antes de confirmar.
  confirmacao?: ConfirmacaoDocumento | null;
  /** Notas já salvas que o aviso de repetição apontou e o usuário confirmou mesmo assim (#93). */
  repeticao_de?: string[];
  criado_em: string;
};

// US-22: um registro da trilha de auditoria.
export type SnapshotExtracao = {
  metodo: "gemini" | "regex";
  confianca?: number | null;
  campos: UploadStructured;
};

export type RegistroAuditoria = {
  _id: string;
  seq: number;
  por: string;
  acao: "documento.extraido" | "documento.confirmado" | "documento.corrigido";
  recurso: { tipo: string; id: string };
  em: string;
  trace_id?: string | null;
  antes?: SnapshotExtracao | null;
  depois: Record<string, unknown>;
  hash: string;
};

export type ConfirmDocumentPayload = {
  email: string;
  amount: number;
  tx_date: string;
  tx_type: TxType;
  cnpj_emitente?: string | null;
  cnpj_destinatario?: string | null;
  description?: string | null;
  source_filename?: string | null;
  ocr_text?: string | null;
  // US-22: liga a confirmação ao documento extraído, para a trilha de auditoria
  // registrar a correção ("de R$ X para R$ Y").
  documento_id?: string | null;
};

export type ConfirmDocumentResponse = {
  limits_transaction: Transaction | null;
  structured_data: UploadStructured;
};

export type UpdateTransactionPayload = {
  amount?: number;
  tx_date?: string;
  source?: string;
  tx_type?: TxType;
};

export type ChatMessage = {
  from: "user" | "agent";
  text: string;
  at: string;
  sources?: string[];
};

export type DemoUser = {
  name: string;
  email: string;
};

export type TokenReason = "document_confirm" | "chat_message";

export type TokenBalance = {
  email: string;
  balance: number;
  costs: Record<TokenReason, number>;
  /** Modo demonstração do billing: saldo nunca bloqueia nem é debitado. */
  ilimitado?: boolean;
};

export type TokenConsumeResult = {
  email: string;
  charged: number;
  balance: number;
  insufficient: boolean;
  ilimitado?: boolean;
};

// GET/PUT /limits/configuracao/{email} (#91). Frações vão de 0 a 1; a margem
// de desenquadramento é o fator sobre o teto (1,2 = 20% acima).
export type ParametrosFiscais = {
  limite_anual: number;
  limite_proporcional: boolean;
  margem_desenquadramento: number;
  limiar_alerta: number;
  meta_mensal: number | null;
  limiar_concentracao_cliente: number;
  dias_minimos_para_projetar: number;
  transacoes_minimas_para_projetar: number;
  dias_abertura_recente: number;
  limiar_lancamento_atipico: number;
  limiar_atencao_ritmo_realizado: number;
};

export type NomeParametro = keyof ParametrosFiscais;

export type ConfiguracaoFiscal = {
  email: string;
  data_abertura: string | null;
  parametros: ParametrosFiscais;
  padrao: ParametrosFiscais;
  personalizados: NomeParametro[];
  /** `false` com a flag desligada no servidor: a configuração é gravada, mas as regras ainda usam o padrão. */
  ativa: boolean;
};

export type AtualizacaoConfiguracao = {
  data_abertura?: string | null;
  /** `null` devolve o campo ao padrão. */
  parametros?: Partial<Record<NomeParametro, number | boolean | null>>;
};
