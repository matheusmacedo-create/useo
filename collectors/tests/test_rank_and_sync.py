from datetime import date
from pathlib import Path

import pytest

from useo.chart import load_history, render_html
from useo.config import SiteConfigError, load_sites
from useo.rank import build_check, run_rank
from useo.runs import recorded_run
from useo.serp import OrganicResult, SerpBatch, SerpResult
from useo.sync import sync_config

REPO = Path(__file__).resolve().parents[2]
DAY = date(2026, 11, 6)


def write_config(tmp_path, termos, devices="[desktop, mobile]", max_kw=100):
    linhas = "".join(f"{t},x\n" for t in termos)
    (tmp_path / "kw.csv").write_text("# comentário\ntermo,tag\n" + linhas)
    (tmp_path / "sites.yaml").write_text(
        f"defaults: {{devices: {devices}, max_keywords: {max_kw}}}\n"
        "sites:\n  - dominio: https://www.Site.com.br/\n    nome: Site\n    keywords: kw.csv\n"
    )
    return tmp_path / "sites.yaml"


def test_repo_config_is_valid():
    sites = load_sites(REPO / "config" / "sites.yaml")
    assert sites[0].dominio == "unicopag.com.br"
    assert {k.device for k in sites[0].keywords} == {"desktop", "mobile"}


def test_load_sites_dedup_and_limit(tmp_path):
    sites = load_sites(write_config(tmp_path, ["A b", "a  B", "c"]))
    assert sites[0].dominio == "site.com.br"
    assert sorted({k.termo for k in sites[0].keywords}) == ["a b", "c"]
    assert len(sites[0].keywords) == 4
    with pytest.raises(SiteConfigError):
        load_sites(write_config(tmp_path, ["a", "b", "c"], max_kw=2))


def test_sync_deactivates_removed_keywords(fake_db, tmp_path):
    sync_config(fake_db, load_sites(write_config(tmp_path, ["a", "b"], devices="[desktop]")))
    assert len(fake_db.tables["keywords"]) == 2
    stats = sync_config(fake_db, load_sites(write_config(tmp_path, ["a"], devices="[desktop]")))
    assert stats["keywords_desativadas"] == 1
    ativos = {k["termo"]: k["ativo"] for k in fake_db.tables["keywords"]}
    assert ativos == {"a": True, "b": False}


def test_build_check_first_url_of_site():
    res = SerpResult(
        key="k",
        organic=[
            OrganicResult(i, i + 1, f"www.d{i}.com", f"https://d{i}.com") for i in range(1, 12)
        ] + [OrganicResult(12, 14, "blog.site.com.br", "https://blog.site.com.br/p")],
        features=["video"],
    )
    c = build_check(res, "site.com.br", "k", DAY)
    assert (c["posicao"], c["posicao_absoluta"]) == (12, 14)
    assert c["top10_dominios"] == [f"d{i}.com" for i in range(1, 11)]
    miss = build_check(SerpResult(key="k"), "site.com.br", "k", DAY)
    assert miss["posicao"] is None and miss["url"] is None


class StubProvider:
    def __init__(self):
        self.calls = []

    def fetch(self, queries):
        self.calls.append(queries)
        results = [
            SerpResult(q.key, [OrganicResult(3, 4, "site.com.br", "https://site.com.br/x")])
            for q in queries[:-1]
        ]
        return SerpBatch(results=results, missing=[queries[-1].key], cost_usd=0.0006 * len(queries))


def test_run_rank_records_and_is_idempotent(fake_db, tmp_path):
    sync_config(fake_db, load_sites(write_config(tmp_path, ["a", "b"])))
    provider = StubProvider()

    with recorded_run(fake_db, "rank") as run:
        stats = run_rank(fake_db, provider, run, day=DAY)
    assert stats["consultadas"] == 4 and stats["gravadas"] == 3
    row = fake_db.tables["runs"][0]
    assert row["status"] == "parcial"
    assert row["custo_usd"] == pytest.approx(0.0024)
    assert row["fim"] is not None

    # 2ª rodada no mesmo dia só consulta a que faltou — e falha porque o stub
    # nunca devolve a última consulta; o run fica registrado como erro.
    with pytest.raises(RuntimeError), recorded_run(fake_db, "rank") as run2:
        run_rank(fake_db, provider, run2, day=DAY)
    assert len(provider.calls[1]) == 1
    assert fake_db.tables["runs"][1]["status"] == "erro"


def test_chart_renders(fake_db, tmp_path):
    sync_config(fake_db, load_sites(write_config(tmp_path, ["a"], devices="[desktop]")))
    kw = fake_db.tables["keywords"][0]["id"]
    for d, p in [("2026-10-30", 15), ("2026-11-05", 9), ("2026-11-06", 7)]:
        fake_db.insert("rank_checks", {"keyword_id": kw, "data": d, "posicao": p, "url": "u"})
    site, rows = load_history(fake_db, "site.com.br", 10, DAY)
    page = render_html(site, rows, 10, DAY)
    assert "<polyline" in page and "▲8" in page
