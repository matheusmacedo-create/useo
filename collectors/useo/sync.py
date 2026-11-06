"""Sincroniza config/ (fonte da verdade, versionada no git) com o banco.

Nada é apagado: site ou keyword que sai da config vira `ativo = false`, e o
histórico de rank_checks continua lá.
"""

from __future__ import annotations

import logging

from useo.config import SiteSpec
from useo.db import Database, in_filter

log = logging.getLogger(__name__)


def sync_config(db: Database, sites: list[SiteSpec]) -> dict[str, int]:
    stats = {"sites": 0, "keywords_ativas": 0, "keywords_desativadas": 0, "sites_desativados": 0}

    rows = db.upsert(
        "sites",
        [
            {
                "dominio": s.dominio,
                "nome": s.nome,
                "ativo": s.ativo,
                "marca": s.marca,
                "concorrentes": s.concorrentes,
            }
            for s in sites
        ],
        on_conflict="dominio",
    ) if sites else []
    ids = {r["dominio"]: r["id"] for r in rows}
    stats["sites"] = len(ids)

    # Sites que estão no banco mas saíram da config.
    for row in db.select("sites", columns="id,dominio", filters={"ativo": "eq.true"}):
        if row["dominio"] not in ids:
            db.update("sites", {"ativo": False}, filters={"id": f"eq.{row['id']}"})
            stats["sites_desativados"] += 1

    for site in sites:
        site_id = ids[site.dominio]
        wanted = [
            {
                "site_id": site_id,
                "termo": k.termo,
                "device": k.device,
                "localizacao": k.localizacao,
                "idioma": k.idioma,
                "tag": k.tag,
                "ativo": True,
            }
            for k in site.keywords
        ]
        kept = db.upsert("keywords", wanted, on_conflict="site_id,termo,device,localizacao") \
            if wanted else []
        kept_ids = {r["id"] for r in kept}
        stats["keywords_ativas"] += len(kept_ids)

        current = db.select(
            "keywords", columns="id", filters={"site_id": f"eq.{site_id}", "ativo": "eq.true"}
        )
        stale = [r["id"] for r in current if r["id"] not in kept_ids]
        if stale:
            db.update("keywords", {"ativo": False}, filters={"id": in_filter(stale)})
            stats["keywords_desativadas"] += len(stale)
        log.info("%s: %d keywords ativas, %d desativadas", site.dominio, len(kept_ids), len(stale))

    return stats
