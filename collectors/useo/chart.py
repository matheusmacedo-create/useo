"""Gráfico de posição (entregável do M2): HTML estático, sem dependências.

Uso: python -m useo chart --site unicopag.com.br --dias 30 --out saida/rank.html
O painel de verdade vem no M6; isto serve pra validar a coleta com olho humano.
"""

from __future__ import annotations

import html
import math
from collections import defaultdict
from datetime import date, timedelta

from useo.db import Database, in_filter
from useo.domains import normalize_domain

MAX_POS = 100  # fora do top 100 é desenhado no fundo


def load_history(db: Database, site: str, days: int, until: date) -> tuple[dict, list[dict]]:
    dominio = normalize_domain(site)
    sites = db.select("sites", columns="id,dominio,nome", filters={"dominio": f"eq.{dominio}"})
    if not sites:
        raise SystemExit(f"site {dominio} não cadastrado (rode `useo sync`)")
    site_row = sites[0]
    keywords = db.select(
        "keywords",
        columns="id,termo,device,tag",
        filters={"site_id": f"eq.{site_row['id']}", "ativo": "eq.true"},
    )
    since = until - timedelta(days=days - 1)
    checks = db.select(
        "rank_checks",
        columns="keyword_id,data,posicao,url",
        filters={
            "keyword_id": in_filter(k["id"] for k in keywords) if keywords else "in.()",
            "and": f"(data.gte.{since.isoformat()},data.lte.{until.isoformat()})",
        },
        order="data",
    ) if keywords else []
    series: dict[str, dict[str, dict]] = defaultdict(dict)
    for c in checks:
        series[c["keyword_id"]][c["data"]] = c
    rows = []
    for k in keywords:
        rows.append({**k, "serie": series.get(k["id"], {})})
    return site_row, rows


def _sparkline(points: list[int | None], width: int = 160, height: int = 36) -> str:
    n = len(points)
    if n == 0 or all(p is None for p in points):
        return '<span class="muted">sem dado</span>'
    step = width / max(n - 1, 1)

    def y(p: int | None) -> float:
        p = MAX_POS if p is None else min(p, MAX_POS)
        # escala log: diferença entre 1 e 10 importa mais que entre 50 e 60
        return 3 + (height - 6) * (math.log(p) / math.log(MAX_POS))

    segs, cur = [], []
    for i, p in enumerate(points):
        if p is None:
            if cur:
                segs.append(cur)
            cur = []
            continue
        cur.append(f"{i * step:.1f},{y(p):.1f}")
    if cur:
        segs.append(cur)
    lines = "".join(
        f'<polyline points="{" ".join(s)}" />' if len(s) > 1
        else f'<circle cx="{s[0].split(",")[0]}" cy="{s[0].split(",")[1]}" r="2" />'
        for s in segs
    )
    guide = f'<line class="g" x1="0" x2="{width}" y1="{y(10):.1f}" y2="{y(10):.1f}" />'
    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'role="img" aria-label="histórico de posição">{guide}{lines}</svg>'
    )


def _fmt_delta(now: int | None, before: int | None) -> str:
    if now is None or before is None:
        return ""
    d = before - now  # positivo = subiu
    if d == 0:
        return '<span class="muted">=</span>'
    cls = "up" if d > 0 else "down"
    return f'<span class="{cls}">{"▲" if d > 0 else "▼"}{abs(d)}</span>'


def render_html(site_row: dict, rows: list[dict], days: int, until: date) -> str:
    dias = [(until - timedelta(days=days - 1 - i)).isoformat() for i in range(days)]

    def last_pos(r):
        for d in reversed(dias):
            if d in r["serie"]:
                return r["serie"][d]["posicao"], d
        return None, None

    body = []
    resumo = defaultdict(int)
    for r in rows:
        pos, d = last_pos(r)
        r["_pos"], r["_dia"] = pos, d
        if d is None:
            resumo["sem dado"] += 1
        elif pos is None:
            resumo["fora do top 100"] += 1
        elif pos <= 3:
            resumo["top 3"] += 1
        elif pos <= 10:
            resumo["4–10"] += 1
        elif pos <= 20:
            resumo["11–20"] += 1
        else:
            resumo["21–100"] += 1

    rows.sort(key=lambda r: (r["_pos"] is None, r["_pos"] or 0, r["termo"], r["device"]))
    for r in rows:
        pts = [r["serie"][d]["posicao"] if d in r["serie"] else None for d in dias]
        week_ago = next(
            (r["serie"][d]["posicao"] for d in reversed(dias[: max(len(dias) - 7, 0)])
             if d in r["serie"]),
            None,
        )
        url = r["serie"].get(r["_dia"], {}).get("url") if r["_dia"] else None
        body.append(
            "<tr>"
            f'<td>{html.escape(r["termo"])}'
            + (f' <span class="tag">{html.escape(r["tag"])}</span>' if r.get("tag") else "")
            + (f'<div class="url">{html.escape(url)}</div>' if url else "")
            + "</td>"
            f'<td>{r["device"]}</td>'
            f'<td class="num">{"—" if r["_pos"] is None else r["_pos"]}</td>'
            f'<td class="num">{_fmt_delta(r["_pos"], week_ago)}</td>'
            f"<td>{_sparkline(pts)}</td>"
            "</tr>"
        )

    ordem = ["top 3", "4–10", "11–20", "21–100", "fora do top 100", "sem dado"]
    tiles = "".join(
        f'<div class="tile"><b>{resumo[k]}</b><span>{k}</span></div>' for k in ordem
    )
    nome = html.escape(site_row.get("nome") or site_row["dominio"])
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Posições {nome}</title>
<style>
:root{{--bg:#fbfaf7;--fg:#1d1d1b;--muted:#7a776f;--line:#e4e1d8;--accent:#2b59c3;
--up:#1f7a3d;--down:#b3261e;--tile:#f1efe8}}
@media (prefers-color-scheme:dark){{:root{{--bg:#151514;--fg:#ecebe6;--muted:#99968d;
--line:#2c2b28;--accent:#8aa9f0;--up:#6fcf8c;--down:#f08a80;--tile:#1f1f1d}}}}
body{{margin:0;background:var(--bg);color:var(--fg);
font:14px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}}
main{{max-width:960px;margin:0 auto;padding:24px 16px}}
h1{{font-size:22px;margin:0 0 4px}} .muted{{color:var(--muted)}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));
gap:8px;margin:20px 0}}
.tile{{background:var(--tile);border-radius:8px;padding:10px 12px}}
.tile b{{display:block;font-size:22px}} .tile span{{color:var(--muted);font-size:12px}}
.wrap{{overflow-x:auto}} table{{width:100%;border-collapse:collapse}}
th,td{{text-align:left;padding:8px 6px;border-bottom:1px solid var(--line);vertical-align:middle}}
th{{font-size:12px;color:var(--muted);font-weight:600}} .num{{text-align:right;
font-variant-numeric:tabular-nums}} .up{{color:var(--up)}} .down{{color:var(--down)}}
.url{{color:var(--muted);font-size:11px;word-break:break-all}}
.tag{{font-size:11px;color:var(--muted);border:1px solid var(--line);
border-radius:4px;padding:0 4px}}
svg polyline{{fill:none;stroke:var(--accent);stroke-width:1.6}} svg circle{{fill:var(--accent)}}
svg .g{{stroke:var(--line);stroke-dasharray:3 3}}
</style></head><body><main>
<h1>{nome}</h1>
<div class="muted">{html.escape(site_row["dominio"])} · Google Brasil · últimos {days} dias
até {until.strftime("%d/%m/%Y")} · linha tracejada = posição 10</div>
<div class="tiles">{tiles}</div>
<div class="wrap"><table>
<thead><tr><th>Keyword</th><th>Device</th><th class="num">Posição</th>
<th class="num">vs 7d</th><th>Histórico</th></tr></thead>
<tbody>{"".join(body)}</tbody></table></div>
</main></body></html>
"""
