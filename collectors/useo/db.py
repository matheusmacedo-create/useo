"""Cliente mínimo do PostgREST do Supabase (service key).

Sem o SDK do Supabase de propósito: só precisamos de select/insert/upsert/update,
e httpx deixa os testes simples (MockTransport).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

import httpx

from useo.settings import SupabaseSettings

Row = dict[str, Any]


class DatabaseError(RuntimeError):
    pass


class Database:
    def __init__(self, settings: SupabaseSettings, client: httpx.Client | None = None):
        self._client = client or httpx.Client(timeout=60)
        self._base = f"{settings.url}/rest/v1"
        self._headers = {
            "apikey": settings.service_key,
            "Authorization": f"Bearer {settings.service_key}",
            "Content-Type": "application/json",
        }

    # -- helpers ---------------------------------------------------------
    def _request(
        self,
        method: str,
        table: str,
        *,
        params: Mapping[str, str] | None = None,
        json: Any = None,
        prefer: str | None = None,
    ) -> list[Row]:
        headers = dict(self._headers)
        if prefer:
            headers["Prefer"] = prefer
        resp = self._client.request(
            method, f"{self._base}/{table}", params=params, json=json, headers=headers
        )
        if resp.status_code >= 400:
            raise DatabaseError(f"{method} {table}: HTTP {resp.status_code} {resp.text[:500]}")
        if not resp.content:
            return []
        data = resp.json()
        return data if isinstance(data, list) else [data]

    # -- API pública -----------------------------------------------------
    def select(
        self,
        table: str,
        *,
        columns: str = "*",
        filters: Mapping[str, str] | None = None,
        order: str | None = None,
        page_size: int = 1000,
    ) -> list[Row]:
        """SELECT paginado. `filters` usa a sintaxe do PostgREST: {"ativo": "eq.true"}."""
        rows: list[Row] = []
        offset = 0
        while True:
            params = {"select": columns, "limit": str(page_size), "offset": str(offset)}
            if order:
                params["order"] = order
            params.update(filters or {})
            page = self._request("GET", table, params=params)
            rows.extend(page)
            if len(page) < page_size:
                return rows
            offset += page_size

    def insert(self, table: str, rows: Row | Sequence[Row]) -> list[Row]:
        return self._request("POST", table, json=rows, prefer="return=representation")

    def upsert(
        self, table: str, rows: Sequence[Row], *, on_conflict: str, chunk: int = 500
    ) -> list[Row]:
        out: list[Row] = []
        for i in range(0, len(rows), chunk):
            out.extend(
                self._request(
                    "POST",
                    table,
                    params={"on_conflict": on_conflict},
                    json=list(rows[i : i + chunk]),
                    prefer="resolution=merge-duplicates,return=representation",
                )
            )
        return out

    def update(self, table: str, values: Row, *, filters: Mapping[str, str]) -> list[Row]:
        if not filters:
            raise ValueError("update sem filtro recusado")
        return self._request(
            "PATCH", table, params=dict(filters), json=values, prefer="return=representation"
        )


def in_filter(values: Iterable[Any]) -> str:
    """Monta 'in.(a,b,c)' para o PostgREST, com aspas para valores com vírgula/espaço."""
    parts = []
    for v in values:
        s = str(v)
        if any(c in s for c in ',()" '):
            s = '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
        parts.append(s)
    return f"in.({','.join(parts)})"
