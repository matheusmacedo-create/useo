"""Normalização e comparação de domínios."""

from __future__ import annotations

from urllib.parse import urlsplit


def normalize_domain(value: str) -> str:
    """'https://www.Unicopag.com.br/x' -> 'unicopag.com.br'."""
    value = value.strip().lower()
    if "://" in value:
        value = urlsplit(value).hostname or ""
    else:
        value = value.split("/", 1)[0]
    value = value.split(":", 1)[0].rstrip(".")
    if value.startswith("www."):
        value = value[4:]
    return value


def belongs_to(candidate: str | None, site_domain: str) -> bool:
    """True se `candidate` é o próprio domínio do site ou um subdomínio dele."""
    if not candidate:
        return False
    cand = normalize_domain(candidate)
    site = normalize_domain(site_domain)
    return cand == site or cand.endswith("." + site)
