"""CLI do Useo.

    useo heartbeat          grava um registro em `runs` (teste do M1)
    useo sync               config/ -> banco (sites e keywords)
    useo rank               rank tracking do dia (M2)
    useo chart --site X     HTML com o histórico de posições
    useo check-cost         falha se o custo de hoje passou do limite
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date
from pathlib import Path

from useo.config import load_sites
from useo.db import Database
from useo.runs import recorded_run
from useo.settings import (
    DataForSeoSettings,
    SupabaseSettings,
    cost_alert_usd,
    load_dotenv,
)


def _db() -> Database:
    return Database(SupabaseSettings.from_env())


def cmd_heartbeat(_: argparse.Namespace) -> int:
    db = _db()
    with recorded_run(db, "base") as run:
        run.detalhe["origem"] = os.environ.get("GITHUB_RUN_ID", "local")
    print(f"run {run.id} gravado")
    return 0


def cmd_sync(_: argparse.Namespace) -> int:
    from useo.sync import sync_config

    db = _db()
    sites = load_sites()
    with recorded_run(db, "sync") as run:
        stats = sync_config(db, sites)
        run.detalhe.update(stats)
    print(stats)
    return 0


def cmd_rank(args: argparse.Namespace) -> int:
    from useo.rank import run_rank
    from useo.serp.dataforseo import DataForSeoProvider

    db = _db()
    provider = DataForSeoProvider(
        DataForSeoSettings.from_env(),
        depth=int(os.environ.get("USEO_SERP_DEPTH", "100")),
        timeout_s=float(os.environ.get("USEO_SERP_TIMEOUT_MIN", "45")) * 60,
    )
    with recorded_run(db, "rank") as run:
        stats = run_rank(
            db,
            provider,
            run,
            day=date.fromisoformat(args.data) if args.data else None,
            site=args.site,
            limit=args.limite,
        )
    print(stats, f"custo US$ {run.custo_usd:.4f}", f"status {run.status}")
    return 0


def cmd_chart(args: argparse.Namespace) -> int:
    from useo.chart import load_history, render_html
    from useo.rank import today_br

    until = date.fromisoformat(args.ate) if args.ate else today_br()
    site_row, rows = load_history(_db(), args.site, args.dias, until)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_html(site_row, rows, args.dias, until), encoding="utf-8")
    print(f"gravado em {out}")
    return 0


def cmd_check_cost(_: argparse.Namespace) -> int:
    from useo.rank import today_br

    db = _db()
    hoje = today_br().isoformat()
    rows = db.select("custo_diario", filters={"dia": f"eq.{hoje}"})
    total = sum(float(r["custo_usd"] or 0) for r in rows)
    limite = cost_alert_usd()
    detalhe = ", ".join(f"{r['modulo']} US$ {float(r['custo_usd']):.4f}" for r in rows) or "nada"
    print(f"custo de {hoje}: US$ {total:.4f} ({detalhe}); limite US$ {limite:.2f}")
    if total > limite:
        # Anotação de erro no GitHub Actions: o job falha e o GitHub avisa por e-mail.
        msg = f"US$ {total:.2f} hoje (limite US$ {limite:.2f})"
        print(f"::error title=Custo acima do limite::{msg}")
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="useo")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("heartbeat", help="grava um run de teste").set_defaults(fn=cmd_heartbeat)
    sub.add_parser("sync", help="sincroniza config/ com o banco").set_defaults(fn=cmd_sync)

    r = sub.add_parser("rank", help="coleta posições do dia")
    r.add_argument("--site", help="só este domínio")
    r.add_argument("--limite", type=int, help="no máximo N consultas (teste barato)")
    r.add_argument("--data", help="AAAA-MM-DD (padrão: hoje em Brasília)")
    r.set_defaults(fn=cmd_rank)

    c = sub.add_parser("chart", help="HTML com histórico de posições")
    c.add_argument("--site", required=True)
    c.add_argument("--dias", type=int, default=30)
    c.add_argument("--ate", help="AAAA-MM-DD (padrão: hoje)")
    c.add_argument("--out", default="saida/rank.html")
    c.set_defaults(fn=cmd_chart)

    sub.add_parser("check-cost", help="alerta de custo diário").set_defaults(fn=cmd_check_cost)
    return p


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
