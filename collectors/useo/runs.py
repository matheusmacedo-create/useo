"""Registro de execução: todo job grava início, fim, status, erro e custo em `runs`."""

from __future__ import annotations

import traceback
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from useo.db import Database


@dataclass
class Run:
    id: int
    modulo: str
    custo_usd: float = 0.0
    status: str = "ok"
    detalhe: dict[str, Any] = field(default_factory=dict)

    def add_cost(self, usd: float) -> None:
        self.custo_usd += float(usd or 0)

    def mark_partial(self, reason: str) -> None:
        self.status = "parcial"
        self.detalhe.setdefault("avisos", []).append(reason)


def _now() -> str:
    return datetime.now(UTC).isoformat()


@contextmanager
def recorded_run(db: Database, modulo: str):
    """Abre uma linha em `runs` e a fecha no fim, mesmo se o job estourar exceção."""
    row = db.insert("runs", {"modulo": modulo, "status": "rodando"})[0]
    run = Run(id=row["id"], modulo=modulo)
    try:
        yield run
    except BaseException as exc:
        db.update(
            "runs",
            {
                "fim": _now(),
                "status": "erro",
                "erro": "".join(traceback.format_exception_only(exc)).strip()[:4000],
                "custo_usd": round(run.custo_usd, 6),
                "detalhe": run.detalhe,
            },
            filters={"id": f"eq.{run.id}"},
        )
        raise
    else:
        db.update(
            "runs",
            {
                "fim": _now(),
                "status": run.status,
                "custo_usd": round(run.custo_usd, 6),
                "detalhe": run.detalhe,
            },
            filters={"id": f"eq.{run.id}"},
        )
