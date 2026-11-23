"""Testes de fusão, reordenação e normalização de listas em verificar_remissoes.py (textos sintéticos)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import pytest
    _SEM_PYTEST = False
except ImportError:
    _SEM_PYTEST = True  # roda também com unittest, sem pytest instalado
    class _Mark:
        @staticmethod
        def parametrize(nomes, casos):
            def deco(f):
                f._parametros = (nomes, casos)
                return f
            return deco
    class pytest:  # noqa: N801
        mark = _Mark()

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verificar_remissoes as vr  # noqa: E402


def _parecer(path: Path, n: int, extra: dict[int, str] | None = None) -> Path:
    """Parecer .md com ``n`` parágrafos numerados de texto distinto; ``extra`` substitui textos."""
    extra = extra or {}
    linhas = [f"{i}. {extra.get(i, f'Texto sintético número {i} sobre o assunto {i * 7}.')}" for i in range(1, n + 1)]
    path.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return path


def _renumerar_texto(mapa: dict, texto: str, tmp_path: Path) -> tuple[str, vr.Renumerador]:
    entrada = tmp_path / "entrada.txt"
    entrada.write_text(texto, encoding="utf-8")
    saida, rn = vr.renumerar({"mapa": {str(k): v for k, v in mapa.items()}, "decisoes": []}, entrada)
    return saida, rn


def _regras(texto: str, total: int = 200) -> list[tuple[str, str]]:
    u = vr.Unidade("teste", texto)
    existentes = {i: f"texto {i}" for i in range(1, total + 1)}
    return [(a.severidade, a.regra) for a in vr._conferir_paragrafos(u, existentes, total)]


# ------------------------------------------------------------- normalizar_lista

@pytest.mark.parametrize("nums, esperado", [
    ([13], "parágrafo 13"),
    ([13, 13], "parágrafo 13"),
    ([82, 72, 82], "parágrafos 72 e 82"),
    ([100, 101], "parágrafos 100 e 101"),
    ([60, 61, 62, 63, 64], "parágrafos 60 a 64"),
    ([48, 49, 50, 60, 61, 62, 63, 64], "parágrafos 48 a 50 e 60 a 64"),
    ([76, 53, 54, 56], "parágrafos 53, 54, 56 e 76"),
    ([90, 90, 105], "parágrafos 90 e 105"),
    ([], ""),
])
def test_normalizar_lista(nums, esperado):
    assert vr.normalizar_lista(nums) == esperado


def test_normalizar_lista_sem_palavra_e_abreviada():
    assert vr.normalizar_lista([72, 82], palavra="") == "72 e 82"
    assert vr.normalizar_lista([5], palavra="pars.") == "par. 5"
    assert vr.normalizar_lista([5, 6, 7], palavra="Parágrafo") == "Parágrafos 5 a 7"


# ------------------------------------------------------------- mapear --origem

def test_mapear_origem_fusao_sem_decisao_e_divisao_pendente(tmp_path):
    antigo = _parecer(tmp_path / "antigo.md", 6)
    # fusão 2+3 -> 2; divisão 5 -> 4 e 5; 6 -> 6; 4 suprimido
    novo = _parecer(tmp_path / "novo.md", 6, {
        1: "Primeiro parágrafo; ver parágrafos 2 e 3.",
        3: "Cita o parágrafo 5 e o parágrafo 4.",
    })
    origem = {"novo_para_antigos": {"1": [1], "2": [2, 3], "3": [1], "4": [5], "5": [5], "6": [6]}}
    res = vr.mapear(antigo, novo, origem=origem)
    assert res["metodo"] == "origem"
    assert res["mapa"]["2"] == [2] and res["mapa"]["3"] == [2]
    assert res["mapa"]["5"] == [4, 5]
    assert res["mapa"]["4"] == []
    assert res["divididos"] == [1, 5]  # 1 também foi para dois novos (1 e 3)
    assert res["suprimidos"] == [4]
    assert res["fundidos"] == {"2": [2, 3]}
    antigos_com_decisao = sorted(d["antigo"] for d in res["decisoes"])
    assert antigos_com_decisao == [4, 5]  # fusão (2, 3) não gera decisão
    d5 = next(d for d in res["decisoes"] if d["antigo"] == 5)
    assert [p["opcao"] for p in d5["partes"]] == ["a", "b"] and [p["numero"] for p in d5["partes"]] == [4, 5]
    assert d5["escolha"] is None


def test_mapear_origem_arquivo_e_cli(tmp_path, capsys):
    antigo = _parecer(tmp_path / "antigo.md", 3)
    novo = _parecer(tmp_path / "novo.md", 2)
    origem = tmp_path / "origem.json"
    origem.write_text(json.dumps({"novo_para_antigos": {"1": [1, 2], "2": [3], "9": [1]}}), encoding="utf-8")
    saida = tmp_path / "mapa.json"
    rc = vr.main(["mapear", "--antigo", str(antigo), "--novo", str(novo), "--origem", str(origem), "--saida", str(saida)])
    assert rc == 0
    res = json.loads(saida.read_text(encoding="utf-8"))
    assert res["mapa"] == {"1": [1, 9], "2": [1], "3": [2]}
    assert any("novo 9" in a for a in res["avisos_origem"])
    ruim = tmp_path / "ruim.json"
    ruim.write_text(json.dumps({"mapa": {}}), encoding="utf-8")
    assert vr.main(["mapear", "--antigo", str(antigo), "--novo", str(novo), "--origem", str(ruim)]) == 2


# ------------------------------------------------------------- renumerar

def test_fusao_20_21_vira_13(tmp_path):
    mapa = {20: [13], 21: [13], 22: [14]}
    saida, rn = _renumerar_texto(mapa, "Ver o parágrafo 20.\nConforme os parágrafos 20 e 21, admite-se.\n", tmp_path)
    assert saida.splitlines() == ["Ver o parágrafo 13.", "Conforme o parágrafo 13, admite-se."]
    assert not rn.pendencias
    assert any("repetido" in a["mensagem"] for a in rn.avisos)


def test_lista_com_fusao_e_renumeracao(tmp_path):
    mapa = {102: [72], 120: [82], 121: [82]}
    saida, _ = _renumerar_texto(mapa, "Nos parágrafos 102, 120 e 121 consta.", tmp_path)
    assert saida == "Nos parágrafos 72 e 82 consta."


def test_intervalo_vira_conjunto_normalizado(tmp_path):
    # 84 a 90 com fusões (85+86 -> 61, 88+89 -> 63) e um suprimido no meio
    mapa = {84: [60], 85: [61], 86: [61], 87: [], 88: [63], 89: [63], 90: [64]}
    saida, rn = _renumerar_texto(mapa, "Ver parágrafos 84 a 90.", tmp_path)
    assert saida == "Ver parágrafos 60, 61, 63 e 64."
    assert not rn.pendencias
    mapa = {84: [60], 85: [61], 86: [62], 87: [62], 88: [63], 89: [64], 90: [64]}
    saida, _ = _renumerar_texto(mapa, "Ver parágrafos 84 a 90 e 95.", tmp_path)
    assert saida == "Ver parágrafos 60 a 64 e 95."


def test_intervalo_que_encolhe_para_dois_ou_um(tmp_path):
    saida, _ = _renumerar_texto({30: [20], 31: [20], 32: [21]}, "Os parágrafos 30 a 32 tratam disso.", tmp_path)
    assert saida == "Os parágrafos 20 e 21 tratam disso."
    saida, _ = _renumerar_texto({30: [20], 31: [20], 32: [20]}, "Os parágrafos 30 a 32 tratam disso.", tmp_path)
    assert saida == "O parágrafo 20 tratam disso."  # o verbo fica para o aviso de concordância


def test_reordenacao_ordena(tmp_path):
    saida, _ = _renumerar_texto({17: [11], 18: [12], 19: [11]}, "Ver parágrafos 18 e 19.", tmp_path)
    assert saida == "Ver parágrafos 11 e 12."


def test_conversao_um_a_um_preserva_forma(tmp_path):
    mapa = {5: [4], 7: [6], 31: [30], 34: [33], 32: [31], 33: [32], 37: [36], 91: [90]}
    saida, _ = _renumerar_texto(mapa, "Ver parágrafos 5 ou 7; e parágrafos 31 a 34, 37 e 91.", tmp_path)
    assert saida == "Ver parágrafos 4 ou 6; e parágrafos 30 a 33, 36 e 90."


def test_renumerar_corrige_repeticao_existente(tmp_path):
    saida, _ = _renumerar_texto({}, "Ver parágrafos 13 e 13; e parágrafos 100 a 101.", tmp_path)
    assert saida == "Ver parágrafo 13; e parágrafos 100 e 101."


def test_lista_json_sem_repeticao_e_ordenada(tmp_path):
    entrada = tmp_path / "anexo.json"
    entrada.write_text(json.dumps({"itens": [{"paragrafos_parecer": [121, 102, 120]}]}), encoding="utf-8")
    saida, _ = vr.renumerar({"mapa": {"102": [72], "120": [82], "121": [82]}, "decisoes": []}, entrada)
    assert json.loads(saida)["itens"][0]["paragrafos_parecer"] == [72, 82]


def test_divisao_continua_exigindo_escolha(tmp_path):
    antigo = _parecer(tmp_path / "antigo.md", 3)
    novo = _parecer(tmp_path / "novo.md", 4, {4: "Remete ao parágrafo 2 e aos parágrafos 1 a 2."})
    origem = {"novo_para_antigos": {"1": [1], "2": [2], "3": [2], "4": [3]}}
    res = vr.mapear(antigo, novo, origem=origem)
    assert [d["antigo"] for d in res["decisoes"]] == [2, 2]
    saida, rn = vr.renumerar(res, novo)
    assert len(rn.pendencias) == 2  # recusa: sem escolha
    res["decisoes"][0]["escolha"] = "b"
    res["decisoes"][1]["escolha"] = "a"  # o intervalo termina na parte "a"
    saida, rn = vr.renumerar(res, novo)
    assert not rn.pendencias
    assert "Remete ao parágrafo 3 e aos parágrafos 1 e 2." in saida
    res["decisoes"][1]["escolha"] = "todas"
    saida, _ = vr.renumerar(res, novo)
    assert "aos parágrafos 1 a 3." in saida


# ------------------------------------------------------------- conferir

def test_conferir_repeticao_bloqueante():
    assert ("bloqueante", "remissao_repetida") in _regras("Ver parágrafos 13 e 13.")
    assert ("bloqueante", "remissao_repetida") in _regras("Ver parágrafos 72, 82 e 82.")
    assert ("bloqueante", "remissao_repetida") in _regras("Ver parágrafos 90, 90 e 105.")
    assert ("bloqueante", "remissao_repetida") in _regras("Ver parágrafos 84 a 90 e 88.")
    assert ("bloqueante", "remissao_repetida") not in _regras("Ver parágrafos 72 e 82.")


def test_conferir_repeticao_mensagem_traz_forma_normalizada():
    u = vr.Unidade("teste", "Ver parágrafos 90, 105 e 105.")
    achados = vr._conferir_paragrafos(u, {i: "x" for i in range(1, 200)}, 199)
    rep = next(a for a in achados if a.regra == "remissao_repetida")
    assert "«parágrafos 90 e 105»" in rep.mensagem


def test_conferir_intervalo_de_dois_alerta():
    u = vr.Unidade("teste", "Ver parágrafos 100 a 101.")
    achados = vr._conferir_paragrafos(u, {i: "x" for i in range(1, 200)}, 199)
    alerta = next(a for a in achados if a.regra == "intervalo_dois")
    assert alerta.severidade == "alerta" and "100 e 101" in alerta.mensagem
    assert ("alerta", "intervalo_dois") not in _regras("Ver parágrafos 100 a 102.")


def test_conferir_fora_de_ordem_alerta():
    assert ("alerta", "remissao_fora_de_ordem") in _regras("Ver parágrafos 120 e 102.")
    assert ("alerta", "remissao_fora_de_ordem") not in _regras("Ver parágrafos 102 e 120.")


def test_conferir_partes_distintas_do_mesmo_paragrafo_nao_e_repeticao():
    u = vr.Unidade("teste", "Ver parágrafos 103, ii, e 103, iii.")
    existentes = {103: "(ii) um; (iii) outro"}
    regras = [a.regra for a in vr._conferir_paragrafos(u, existentes, 103)]
    assert "remissao_repetida" not in regras


def test_conferir_cli_bloqueia_repeticao(tmp_path, capsys):
    parecer = _parecer(tmp_path / "parecer.md", 15, {15: "Conforme parágrafos 13 e 13, conclui-se."})
    assert vr.main(["conferir", "--parecer", str(parecer)]) == 1
    assert "remissao_repetida" in capsys.readouterr().out


# ---- execução sem pytest: `python3 -m unittest test_verificar_remissoes_fusao` ----
import contextlib as _ctx, inspect as _insp, io as _io, tempfile as _tf, unittest as _ut


class _Capsys:
    def __init__(self, buf):
        self._buf = buf

    def readouterr(self):
        class _R:
            pass
        r = _R(); r.out = self._buf.getvalue(); r.err = ""
        self._buf.seek(0); self._buf.truncate()
        return r


def _rodar(f, args):
    params = _insp.signature(f).parameters
    kw = {}
    with _tf.TemporaryDirectory() as d:
        buf = _io.StringIO()
        if "tmp_path" in params:
            kw["tmp_path"] = Path(d)
        if "capsys" in params:
            kw["capsys"] = _Capsys(buf)
        with _ctx.redirect_stdout(buf):
            f(*args, **kw)


class TestSemPytest(_ut.TestCase):
    pass


for _nome, _f in (list(globals().items()) if _SEM_PYTEST else []):
    if _nome.startswith("test_") and callable(_f):
        _casos = getattr(_f, "_parametros", None)
        if _casos:
            for _i, _c in enumerate(_casos[1]):
                setattr(TestSemPytest, f"{_nome}_{_i}", (lambda f, c: lambda self: _rodar(f, c))(_f, _c))
        else:
            setattr(TestSemPytest, _nome, (lambda f: lambda self: _rodar(f, ()))(_f))
