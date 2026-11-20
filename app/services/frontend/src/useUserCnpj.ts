import { useLocalStorage } from "./hooks/useLocalStorage";

// CNPJ fictício usado como padrão na demo. O usuário pode trocar pelo CNPJ
// real do seu MEI para que o sistema detecte automaticamente se um
// documento enviado é uma venda (usuário é o emitente) ou uma compra
// (usuário é o destinatário).
export const DEMO_CNPJ_PLACEHOLDER = "12.345.678/0001-90";

export function useUserCnpj() {
  return useLocalStorage<string>("demo-user-cnpj", DEMO_CNPJ_PLACEHOLDER);
}
