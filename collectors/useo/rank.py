"""M2 — rank tracking diário.

Para cada keyword ativa de site ativo: consulta a SERP, acha a primeira URL do
site entre os orgânicos e grava em rank_checks (uma linha por keyword por dia).
Rodar de novo no mesmo dia só consulta o que ainda falta.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from useo.db import Database, in_filter
from useo.domains import belongs_to, normalize_domain
from useo.runs import Run
from useo.serp import SerpProvider, SerpQuery, SerpResult

log = logging.getLogger(__name__)
TZ = ZoneInfo("America/Sao_Paulo")


def today_br() -> date:
    return datetime.now(TZ).date()


def build_check(result: SerpResult, site_domain: str, keyword_id: str, day: date) -> dict:
    hit = next((o for o in result.organic if belongs_to(o.domain or o.url, site_domain)), None)
    top10: list[str] = []
    for o in result.organic:
        if o.rank_group > 10:
            break
        top10.append(normalize_domain(o.domain or o.url))
    return {
        "keyword_id": keyword_id,
        "data": day.isoformat(),
        "posicao": hit.rank_group if hit else None,
        "posicao_absoluta": hit.rank_absolute if hit else None,
        "url": hit.url if hit else None,
        "serp_features": result.features,
        "top10_dominios": top10,
    }


def load_pending_keywords(db: Database, day: date, site: str | None = None) -> list[dict]:
    site_filters = {"ativo": "eq.true"}
    if site:
        site_filters["dominio"] = f"eq.{normalize_domain(site)}"
    sites = {s["id"]: s["dominio"] for s in db.select("sites", columns="id,dominio",
                                                         filters=site_filters)}
    if not sites:
        return []
    keywords = db.select(
        "keywords",
        columns="id,site_id,termo,device,localizacao,idioma",
        filters={"ativo": "eq.true", "site_id": in_filter(sites)},
        order="site_id,termo,device",
    )
    done = {
        r["keyword_id"]
        for r in db.select(
            "rank_checks", columns="keyword_id", filters={"data": f"eq.{day.isoformat()}"}
        )
    }
    out = []
    for k in keywords:
        if k["id"] in done:
            continue
        out.append({**k, "dominio": sites[k["site_id"]]})
    return out


def run_rank(
    db: Database,
    provider: SerpProvider,
    run: Run,
    *,
    day: date | None = None,
    site: str | None = None,
    limit: int | None = None,
) -> dict[str, int]:
    day = day or today_br()
    pending = load_pending_keywords(db, day, site)
    if limit:
        pending = pending[:limit]
    run.detalhe.update({"data": day.isoformat(), "keywords": len(pending)})
    if not pending:
        log.info("nada a coletar para %s", day)
        return {"consultadas": 0, "gravadas": 0}

    by_id = {k["id"]: k for k in pending}
    queries = [
        SerpQuery(
            key=k["id"],
            keyword=k["termo"],
            device=k["device"],
            location_code=k["localizacao"],
            language_code=k["idioma"],
        )
        for k in pending
    ]
    batch = provider.fetch(queries)
    run.add_cost(batch.cost_usd)

    checks = [
        build_check(r, by_id[r.key]["dominio"], r.key, day) for r in batch.results if r.key in by_id
    ]
    if checks:
        db.upsert("rank_checks", checks, on_conflict="keyword_id,data")

    ranked = sum(1 for c in checks if c["posicao"] is not None)
    stats = {
        "consultadas": len(queries),
        "gravadas": len(checks),
        "no_top": ranked,
        "sem_resultado": len(batch.missing),
        "erros": len(batch.errors),
    }
    run.detalhe.update(stats)
    if batch.missing or batch.errors:
        run.mark_partial(f"{len(batch.missing)} sem resultado no prazo, {len(batch.errors)} erros")
        run.detalhe["erros_amostra"] = dict(list(batch.errors.items())[:10])
    log.info("rank %s: %s, custo US$ %.4f", day, stats, batch.cost_usd)
    if not checks:
        raise RuntimeError(f"nenhuma SERP coletada de {len(queries)} consultas: {stats}")
    return stats
