"""Leitura de config/sites.yaml e das listas de keywords (CSV)."""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from useo.domains import normalize_domain
from useo.settings import REPO_ROOT

DEVICES = ("desktop", "mobile")


class SiteConfigError(ValueError):
    pass


@dataclass(frozen=True)
class KeywordSpec:
    termo: str
    device: str
    localizacao: int
    idioma: str
    tag: str | None = None


@dataclass
class SiteSpec:
    dominio: str
    nome: str
    ativo: bool = True
    marca: list[str] = field(default_factory=list)
    concorrentes: list[str] = field(default_factory=list)
    keywords: list[KeywordSpec] = field(default_factory=list)


def config_dir() -> Path:
    return Path(os.environ.get("USEO_CONFIG_DIR", REPO_ROOT / "config"))


def read_keywords_csv(path: Path) -> list[tuple[str, str | None]]:
    """CSV com cabeçalho `termo,tag`. Linhas começando com # são ignoradas."""
    lines = [
        ln for ln in path.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    ]
    out: list[tuple[str, str | None]] = []
    seen: set[str] = set()
    for row in csv.DictReader(lines):
        termo = " ".join((row.get("termo") or "").split()).lower()
        if not termo or termo in seen:
            continue
        seen.add(termo)
        out.append((termo, (row.get("tag") or "").strip() or None))
    return out


def load_sites(path: Path | None = None) -> list[SiteSpec]:
    path = path or config_dir() / "sites.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    defaults = data.get("defaults") or {}
    max_kw = int(defaults.get("max_keywords", 100))

    sites: list[SiteSpec] = []
    for raw in data.get("sites") or []:
        dominio = normalize_domain(raw["dominio"])
        devices = raw.get("devices", defaults.get("devices", list(DEVICES)))
        bad = set(devices) - set(DEVICES)
        if bad:
            raise SiteConfigError(f"{dominio}: device inválido {sorted(bad)}")
        loc = int(raw.get("location_code", defaults.get("location_code", 2076)))
        lang = raw.get("language_code", defaults.get("language_code", "pt"))

        termos: list[tuple[str, str | None]] = []
        if raw.get("keywords"):
            termos = read_keywords_csv(path.parent / raw["keywords"])
        if len(termos) > max_kw:
            raise SiteConfigError(
                f"{dominio}: {len(termos)} keywords, limite é {max_kw} (defaults.max_keywords)"
            )

        sites.append(
            SiteSpec(
                dominio=dominio,
                nome=raw.get("nome") or dominio,
                ativo=bool(raw.get("ativo", True)),
                marca=list(raw.get("marca") or []),
                concorrentes=[normalize_domain(c) for c in raw.get("concorrentes") or []],
                keywords=[
                    KeywordSpec(termo=t, device=d, localizacao=loc, idioma=lang, tag=tag)
                    for t, tag in termos
                    for d in devices
                ],
            )
        )
    dominios = [s.dominio for s in sites]
    if len(dominios) != len(set(dominios)):
        raise SiteConfigError("domínio repetido em sites.yaml")
    return sites
