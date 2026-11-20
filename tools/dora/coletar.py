import argparse
import json
import os
import re
from datetime import datetime, timedelta, timezone

import httpx

def get_recent_prs(repo: str, token: str, days: int):
    url = f"https://api.github.com/repos/{repo}/pulls"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"Bearer {token}"
    }

    since = datetime.now(timezone.utc) - timedelta(days=days)
    prs = []
    page = 1

    while True:
        resp = httpx.get(f"{url}?state=closed&per_page=100&page={page}", headers=headers)
        if resp.status_code != 200:
            break

        data = resp.json()
        if not data:
            break

        for pr in data:
            if not pr.get("merged_at"):
                continue

            merged_at = datetime.fromisoformat(pr["merged_at"].replace("Z", "+00:00"))
            if merged_at < since:
                return prs

            prs.append(pr)

        page += 1

    return prs


def get_pr_commits(repo: str, pr_number: int, token: str):
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/commits"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"Bearer {token}"
    }
    resp = httpx.get(url, headers=headers)
    if resp.status_code != 200:
        return []
    return resp.json()


def calculate_lead_time(prs, repo, token):
    if not prs:
        return 0

    total_seconds = 0
    count = 0

    for pr in prs:
        commits = get_pr_commits(repo, pr["number"], token)
        if not commits:
            continue

        first_commit_date = datetime.fromisoformat(
            commits[0]["commit"]["author"]["date"].replace("Z", "+00:00")
        )
        merged_at = datetime.fromisoformat(pr["merged_at"].replace("Z", "+00:00"))

        total_seconds += (merged_at - first_commit_date).total_seconds()
        count += 1

    return total_seconds / count if count > 0 else 0


def calculate_metrics(repo, days, token):
    prs = get_recent_prs(repo, token, days)

    # 1. Deployment Frequency (deploys per week)
    # Assumimos que cada merge na main resulta em um deploy (por US-07)
    weeks = days / 7
    deployment_frequency = len(prs) / weeks if weeks > 0 else 0

    # 2. Lead Time for Changes (em horas)
    lead_time_seconds = calculate_lead_time(prs, repo, token)
    lead_time_hours = lead_time_seconds / 3600

    # 3. Change Failure Rate (percentual)
    # Estimativa básica: PRs com 'fix' no título indicam correções de falhas recentes.
    # Em um cenário real, usariamos labels de incidentes.
    failures = sum(1 for pr in prs if re.match(r"^fix\(|^hotfix", pr["title"].lower()))
    change_failure_rate = (failures / len(prs) * 100) if prs else 0

    # 4. Time to Restore Service (em horas)
    # Media de tempo de resolução para os PRs classificados como 'fix'
    fix_prs = [pr for pr in prs if re.match(r"^fix\(|^hotfix", pr["title"].lower())]
    time_to_restore_seconds = calculate_lead_time(fix_prs, repo, token)
    time_to_restore_hours = time_to_restore_seconds / 3600

    return {
        "deployment_frequency_weekly": deployment_frequency,
        "lead_time_hours": lead_time_hours,
        "change_failure_rate_percent": change_failure_rate,
        "time_to_restore_hours": time_to_restore_hours,
        "total_deployments": len(prs),
        "period_days": days,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


def write_prometheus_metrics(metrics, out_file, repo):
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        f.write("# HELP dora_deployment_frequency_weekly Deployment frequency (deploys per week)\n")
        f.write("# TYPE dora_deployment_frequency_weekly gauge\n")
        f.write(f'dora_deployment_frequency_weekly{{repo="{repo}"}} {metrics["deployment_frequency_weekly"]:.4f}\n')

        f.write("# HELP dora_lead_time_hours Lead time for changes (hours)\n")
        f.write("# TYPE dora_lead_time_hours gauge\n")
        f.write(f'dora_lead_time_hours{{repo="{repo}"}} {metrics["lead_time_hours"]:.4f}\n')

        f.write("# HELP dora_change_failure_rate_percent Change failure rate (percentage)\n")
        f.write("# TYPE dora_change_failure_rate_percent gauge\n")
        f.write(f'dora_change_failure_rate_percent{{repo="{repo}"}} {metrics["change_failure_rate_percent"]:.4f}\n')

        f.write("# HELP dora_time_to_restore_hours Time to restore service (hours)\n")
        f.write("# TYPE dora_time_to_restore_hours gauge\n")
        f.write(f'dora_time_to_restore_hours{{repo="{repo}"}} {metrics["time_to_restore_hours"]:.4f}\n')


def main():
    parser = argparse.ArgumentParser(description="Coletor de métricas DORA")
    parser.add_argument("--repo", required=True, help="Repositório (owner/repo)")
    parser.add_argument("--janela-dias", type=int, default=28, help="Janela de análise em dias")
    parser.add_argument("--saida", required=True, help="Arquivo de saída JSON")
    parser.add_argument("--saida-prometheus", required=True, help="Arquivo de saída Prometheus")
    args = parser.parse_args()

    token = os.environ.get("GH_TOKEN")
    if not token:
        print("Aviso: GH_TOKEN não definido. Usando limite de taxa anônimo.")
        token = ""

    metrics = calculate_metrics(args.repo, args.janela_dias, token)

    os.makedirs(os.path.dirname(args.saida), exist_ok=True)
    with open(args.saida, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    write_prometheus_metrics(metrics, args.saida_prometheus, args.repo)
    print(f"Métricas coletadas e salvas em {args.saida}")


if __name__ == "__main__":
    main()
