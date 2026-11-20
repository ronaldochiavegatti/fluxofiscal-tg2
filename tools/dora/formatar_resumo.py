import argparse
import json
import sys

def main():
    parser = argparse.ArgumentParser(description="Formatar resumo DORA em Markdown")
    parser.add_argument("json_file", help="Arquivo JSON de entrada")
    args = parser.parse_args()

    try:
        with open(args.json_file, "r", encoding="utf-8") as f:
            metrics = json.load(f)
    except FileNotFoundError:
        print(f"Erro: Arquivo {args.json_file} não encontrado.")
        sys.exit(1)

    print("## Métricas DORA")
    print(f"Período de análise: últimos **{metrics['period_days']} dias**")
    print()
    print("| Métrica | Valor Atual | Alvo |")
    print("| :--- | :--- | :--- |")

    # Format and compare with targets
    freq = metrics['deployment_frequency_weekly']
    freq_status = "✅" if freq >= 3 else "⚠️"
    print(f"| Frequência de implantação | {freq:.1f}/semana {freq_status} | > 3/semana |")

    lead = metrics['lead_time_hours']
    lead_status = "✅" if lead <= 24 else "⚠️"
    print(f"| Lead time para mudanças | {lead:.1f}h {lead_status} | < 24h |")

    cfr = metrics['change_failure_rate_percent']
    cfr_status = "✅" if cfr <= 15 else "⚠️"
    print(f"| Taxa de falha de mudanças | {cfr:.1f}% {cfr_status} | < 15% |")

    ttr = metrics['time_to_restore_hours']
    ttr_status = "✅" if ttr <= 1 else "⚠️"
    print(f"| Tempo para restaurar | {ttr:.1f}h {ttr_status} | < 1h |")

    print()
    print(f"*Total de implantações no período: {metrics['total_deployments']}*")
    print(f"*Coletado em: {metrics['timestamp']}*")

if __name__ == "__main__":
    main()
