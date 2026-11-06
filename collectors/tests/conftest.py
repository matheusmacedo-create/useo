"""FakeDB: implementa a interface de useo.db.Database em memória."""

from __future__ import annotations

import itertools
import uuid
from typing import Any

import pytest

from useo.db import Database

UUID_TABLES = {"sites", "keywords", "prompts", "audits"}


def _parse_in(expr: str) -> set[str]:
    inner = expr[len("in.("):-1]
    return {p.strip('"') for p in inner.split(",") if p}


def _match(row: dict, key: str, expr: str) -> bool:
    if key == "and":
        conds = expr.strip("()").split(",")
        for cond in conds:
            col, op, val = cond.split(".", 2)
            v = str(row.get(col))
            if op == "gte" and not v >= val:
                return False
            if op == "lte" and not v <= val:
                return False
        return True
    op, _, val = expr.partition(".")
    cur = row.get(key)
    if op == "eq":
        if isinstance(cur, bool):
            return str(cur).lower() == val
        return str(cur) == val
    if op == "in":
        return str(cur) in _parse_in(expr)
    raise NotImplementedError(expr)


class FakeDB(Database):
    def __init__(self):  # noqa: D401 — sem HTTP
        self.tables: dict[str, list[dict[str, Any]]] = {}
        self._ids = itertools.count(1)

    def _t(self, table):
        return self.tables.setdefault(table, [])

    def _new_id(self, table):
        return str(uuid.uuid4()) if table in UUID_TABLES else next(self._ids)

    def select(self, table, *, columns="*", filters=None, order=None, page_size=1000):
        rows = [
            r for r in self._t(table)
            if all(_match(r, k, v) for k, v in (filters or {}).items())
        ]
        return [dict(r) for r in rows]

    def insert(self, table, rows):
        rows = [rows] if isinstance(rows, dict) else rows
        out = []
        for r in rows:
            row = {"id": self._new_id(table), **r}
            self._t(table).append(row)
            out.append(dict(row))
        return out

    def upsert(self, table, rows, *, on_conflict, chunk=500):
        keys = on_conflict.split(",")
        out = []
        for r in rows:
            existing = next(
                (e for e in self._t(table) if all(str(e.get(k)) == str(r.get(k)) for k in keys)),
                None,
            )
            if existing:
                existing.update(r)
                out.append(dict(existing))
            else:
                out.extend(self.insert(table, [r]))
        return out

    def update(self, table, values, *, filters):
        out = []
        for r in self._t(table):
            if all(_match(r, k, v) for k, v in filters.items()):
                r.update(values)
                out.append(dict(r))
        return out


@pytest.fixture
def fake_db():
    return FakeDB()
