"""Contrato de um provedor de SERP.

Trocar DataForSEO por SerpApi (ou outro) = escrever outro arquivo que implemente
`SerpProvider` e devolva `SerpResult`. O resto do coletor não muda.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class SerpQuery:
    key: str  # identificador nosso (keyword_id); volta no resultado
    keyword: str
    device: str = "desktop"  # desktop | mobile
    location_code: int = 2076  # Brasil
    language_code: str = "pt"


@dataclass(frozen=True)
class OrganicResult:
    rank_group: int  # posição entre os orgânicos
    rank_absolute: int  # posição entre todos os blocos da SERP
    domain: str
    url: str


@dataclass
class SerpResult:
    key: str
    organic: list[OrganicResult] = field(default_factory=list)
    features: list[str] = field(default_factory=list)  # tipos de bloco além de "organic"


@dataclass
class SerpBatch:
    results: list[SerpResult] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)  # keys sem resultado no prazo
    errors: dict[str, str] = field(default_factory=dict)  # key -> mensagem
    cost_usd: float = 0.0


class SerpProvider(Protocol):
    def fetch(self, queries: Sequence[SerpQuery]) -> SerpBatch: ...
