"""Testa o auditor de feature flags (US-16).

Cobre os dois cenários de aceite da história — flag usada mas não declarada
reprova o PR; flag vencida é detectada para a issue automática — e a
validação do inventário que sustenta os dois.
"""

import datetime as dt
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import auditar as au  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]


def _flag(**over):
    base = {
        "nome": "dashboard-v2",
        "tipo": "release",
        "descricao": "descricao",
        "quando_desligada": "comportamento antigo",
        "servicos": ["frontend"],
        "padrao_seguro": False,
        "remover_ate": dt.date(2099, 1, 1),
    }
    base.update(over)
    return base


# ---------------------------------------------------------------------------
# validar_declaracoes
# ---------------------------------------------------------------------------


def test_declaracao_valida_nao_gera_problema():
    assert au.validar_declaracoes([_flag()]) == []


def test_campo_obrigatorio_ausente():
    flag = _flag()
    del flag["descricao"]
    problemas = au.validar_declaracoes([flag])
    assert any("descricao" in p for p in problemas)


def test_nome_duplicado():
    problemas = au.validar_declaracoes([_flag(), _flag()])
    assert any("declarada mais de uma vez" in p for p in problemas)


def test_nome_fora_de_kebab_case():
    problemas = au.validar_declaracoes([_flag(nome="Dashboard_V2")])
    assert any("kebab-case" in p for p in problemas)


def test_tipo_invalido():
    problemas = au.validar_declaracoes([_flag(tipo="permanente-para-sempre")])
    assert any("tipo inválido" in p for p in problemas)


@pytest.mark.parametrize("tipo", ["release", "experiment"])
def test_release_e_experiment_exigem_remover_ate(tipo: str):
    flag = _flag(tipo=tipo)
    del flag["remover_ate"]
    problemas = au.validar_declaracoes([flag])
    assert any("remover_ate" in p for p in problemas)


@pytest.mark.parametrize("tipo", ["ops", "permission"])
def test_ops_e_permission_nao_podem_ter_remover_ate(tipo: str):
    problemas = au.validar_declaracoes([_flag(tipo=tipo, remover_ate=dt.date(2099, 1, 1))])
    assert any("permanente" in p for p in problemas)


def test_falta_padrao_seguro():
    flag = _flag()
    del flag["padrao_seguro"]
    problemas = au.validar_declaracoes([flag])
    assert any("padrao_seguro" in p for p in problemas)


# ---------------------------------------------------------------------------
# varrer_codigo
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "linha",
    [
        'is_enabled("dashboard-v2")',
        'esta_ativa("dashboard-v2", padrao=False)',
        "useFlag('dashboard-v2')",
        'useFeatureFlag("dashboard-v2", true)',
    ],
)
def test_varrer_codigo_reconhece_todos_os_padroes(tmp_path: Path, linha: str):
    (tmp_path / "arquivo.py").write_text(linha, encoding="utf-8")
    usos = au.varrer_codigo(tmp_path)
    assert "dashboard-v2" in usos


def test_varrer_codigo_ignora_node_modules(tmp_path: Path):
    ignorado = tmp_path / "node_modules" / "pacote"
    ignorado.mkdir(parents=True)
    (ignorado / "arquivo.js").write_text('useFlag("nao-conta")', encoding="utf-8")
    assert au.varrer_codigo(tmp_path) == {}


def test_varrer_codigo_ignora_extensao_desconhecida(tmp_path: Path):
    (tmp_path / "notas.md").write_text('is_enabled("nao-conta")', encoding="utf-8")
    assert au.varrer_codigo(tmp_path) == {}


# ---------------------------------------------------------------------------
# modo_estrito — os dois cenários de aceite da US-16
# ---------------------------------------------------------------------------


def test_estrito_reprova_flag_usada_e_nao_declarada(tmp_path: Path):
    (tmp_path / "servico.py").write_text('is_enabled("recurso-novo")', encoding="utf-8")
    assert au.modo_estrito([_flag()], tmp_path) == 1


def test_estrito_aprova_flag_declarada_e_usada(tmp_path: Path):
    (tmp_path / "servico.py").write_text('is_enabled("dashboard-v2")', encoding="utf-8")
    assert au.modo_estrito([_flag()], tmp_path) == 0


def test_estrito_aprova_flag_declarada_e_ainda_sem_uso(tmp_path: Path):
    """Neste projeto as flags são declaradas junto do planejamento da onda,
    antes da implementação — declarada e não usada não é erro."""
    assert au.modo_estrito([_flag()], tmp_path) == 0


def test_estrito_reprova_declaracao_malformada(tmp_path: Path):
    flag = _flag()
    del flag["padrao_seguro"]
    assert au.modo_estrito([flag], tmp_path) == 1


# ---------------------------------------------------------------------------
# flags_vencidas — a outra metade do cenário de aceite
# ---------------------------------------------------------------------------


def test_flags_vencidas_encontra_prazo_estourado():
    hoje = dt.date(2026, 9, 1)
    vencida = _flag(nome="antiga", remover_ate=dt.date(2026, 8, 1))
    no_prazo = _flag(nome="nova", remover_ate=dt.date(2027, 1, 1))

    resultado = au.flags_vencidas([vencida, no_prazo], hoje)

    assert len(resultado) == 1
    flag, dias = resultado[0]
    assert flag["nome"] == "antiga"
    assert dias == 31


def test_flags_vencidas_ordena_da_mais_atrasada():
    hoje = dt.date(2026, 9, 1)
    pouco_atrasada = _flag(nome="pouco", remover_ate=dt.date(2026, 8, 25))
    muito_atrasada = _flag(nome="muito", remover_ate=dt.date(2026, 1, 1))

    resultado = au.flags_vencidas([pouco_atrasada, muito_atrasada], hoje)

    assert [f["nome"] for f, _ in resultado] == ["muito", "pouco"]


def test_flags_vencidas_ignora_permanentes_sem_remover_ate():
    permanente = _flag(nome="ops-x", tipo="ops", remover_ate=None)
    assert au.flags_vencidas([permanente], dt.date(2099, 1, 1)) == []


# ---------------------------------------------------------------------------
# modo_vencidas — não reprova o pipeline, só relata e (opcionalmente) abre issue
# ---------------------------------------------------------------------------


def test_modo_vencidas_sem_flag_vencida_nao_reprova():
    assert au.modo_vencidas([_flag(remover_ate=dt.date(2099, 1, 1))], repo=None, criar=False) == 0


def test_modo_vencidas_com_vencida_ainda_nao_reprova_sem_criar():
    vencida = _flag(remover_ate=dt.date(2000, 1, 1))
    assert au.modo_vencidas([vencida], repo=None, criar=False) == 0


def test_modo_vencidas_exige_repo_para_abrir_issue():
    vencida = _flag(remover_ate=dt.date(2000, 1, 1))
    assert au.modo_vencidas([vencida], repo=None, criar=True) == 1


def test_abrir_issue_nao_duplica_quando_ja_existe(monkeypatch: pytest.MonkeyPatch):
    chamadas: list[list[str]] = []

    def _run_falso(cmd, capture_output=False, text=False, check=False):
        chamadas.append(cmd)
        if "issue" in cmd and "list" in cmd:
            return subprocess.CompletedProcess(
                cmd, 0, stdout='[{"title": "chore: remover a feature flag vencida \'antiga\'"}]'
            )
        raise AssertionError(f"não deveria chamar: {cmd}")

    monkeypatch.setattr(au.subprocess, "run", _run_falso)
    au.abrir_issue("dono/repo", _flag(nome="antiga"), dias=10)

    # Só a checagem de existência foi chamada — nenhuma tentativa de criar.
    assert len(chamadas) == 1
    assert "create" not in chamadas[0]


# ---------------------------------------------------------------------------
# erro() / carregar_inventario — saída de erro é sys.exit(2), não exceção solta
# ---------------------------------------------------------------------------


def test_inventario_ausente_sai_com_erro(tmp_path: Path):
    with pytest.raises(SystemExit) as exc:
        au.carregar_inventario(tmp_path / "nao-existe.yaml")
    assert exc.value.code == 2


def test_inventario_real_do_projeto_e_valido():
    """O próprio docs/feature-flags.yaml do projeto não pode reprovar a
    validação — é a garantia mínima de que o inventário está bem formado."""
    flags = au.carregar_inventario(RAIZ / "docs" / "feature-flags.yaml")
    assert au.validar_declaracoes(flags) == []
