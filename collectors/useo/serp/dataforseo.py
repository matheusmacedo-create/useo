"""DataForSEO — Google Organic SERP API, modo fila (Standard Queue).

Fluxo: task_post (lotes de até 100) → tasks_ready (polling) → task_get/advanced.
O modo fila é o mais barato e cabe num job noturno; o custo de cada tarefa vem
na resposta do task_post e é somado em `SerpBatch.cost_usd`.

Docs: https://docs.dataforseo.com/v3/serp/google/organic/task_post/
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from typing import Any

import httpx

from useo.serp.base import OrganicResult, SerpBatch, SerpQuery, SerpResult
from useo.settings import DataForSeoSettings

log = logging.getLogger(__name__)

API = "https://api.dataforseo.com/v3/serp/google/organic"
POST_BATCH = 100  # limite da API por chamada
OK = 20000
CREATED = 20100
NOT_READY = {40601, 40602}  # Task Handed / Task In Queue


class DataForSeoError(RuntimeError):
    pass


class DataForSeoProvider:
    def __init__(
        self,
        settings: DataForSeoSettings,
        *,
        depth: int = 100,
        timeout_s: float = 45 * 60,
        poll_every_s: float = 30,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._client = client or httpx.Client(
            timeout=60, auth=(settings.login, settings.password)
        )
        self.depth = depth
        self.timeout_s = timeout_s
        self.poll_every_s = poll_every_s
        self._sleep = sleep
        self._clock = clock

    # -- HTTP ------------------------------------------------------------
    def _call(self, method: str, path: str, json: Any = None) -> dict[str, Any]:
        resp = self._client.request(method, f"{API}{path}", json=json)
        if resp.status_code >= 400:
            raise DataForSeoError(f"{method} {path}: HTTP {resp.status_code} {resp.text[:300]}")
        body = resp.json()
        if body.get("status_code") != OK:
            raise DataForSeoError(
                f"{method} {path}: {body.get('status_code')} {body.get('status_message')}"
            )
        return body

    # -- etapas ----------------------------------------------------------
    def _task_payload(self, q: SerpQuery) -> dict[str, Any]:
        return {
            "keyword": q.keyword,
            "location_code": q.location_code,
            "language_code": q.language_code,
            "device": q.device,
            "os": "android" if q.device == "mobile" else "windows",
            "depth": self.depth,
            "priority": 1,  # fila normal (a mais barata)
            "tag": q.key,
        }

    def post(self, queries: Sequence[SerpQuery], batch: SerpBatch) -> dict[str, str]:
        """Enfileira as consultas. Devolve {task_id: key}."""
        pending: dict[str, str] = {}
        for i in range(0, len(queries), POST_BATCH):
            chunk = queries[i : i + POST_BATCH]
            body = self._call("POST", "/task_post", json=[self._task_payload(q) for q in chunk])
            for task in body.get("tasks") or []:
                key = (task.get("data") or {}).get("tag")
                batch.cost_usd += float(task.get("cost") or 0)
                if task.get("status_code") == CREATED and task.get("id"):
                    pending[task["id"]] = key
                elif key:
                    batch.errors[key] = f"{task.get('status_code')} {task.get('status_message')}"
        return pending

    def ready_ids(self) -> set[str]:
        body = self._call("GET", "/tasks_ready")
        ids: set[str] = set()
        for task in body.get("tasks") or []:
            for item in task.get("result") or []:
                if item.get("id"):
                    ids.add(item["id"])
        return ids

    def get(self, task_id: str) -> tuple[str, dict[str, Any] | None]:
        """Devolve (status, result). status: 'ok' | 'pending' | mensagem de erro."""
        body = self._call("GET", f"/task_get/advanced/{task_id}")
        task = (body.get("tasks") or [{}])[0]
        code = task.get("status_code")
        if code == OK:
            result = (task.get("result") or [None])[0]
            return "ok", result or {}
        if code in NOT_READY:
            return "pending", None
        return f"{code} {task.get('status_message')}", None

    # -- orquestração ----------------------------------------------------
    def fetch(self, queries: Sequence[SerpQuery]) -> SerpBatch:
        batch = SerpBatch()
        if not queries:
            return batch
        pending = self.post(queries, batch)
        log.info("DataForSEO: %d tarefas enfileiradas (US$ %.4f)", len(pending), batch.cost_usd)

        deadline = self._clock() + self.timeout_s
        while pending and self._clock() < deadline:
            self._sleep(self.poll_every_s)
            for task_id in self.ready_ids() & pending.keys():
                self._collect(task_id, pending, batch)
            log.info("DataForSEO: faltam %d", len(pending))

        # Última tentativa direta (tasks_ready pode ter perdido alguma).
        for task_id in list(pending):
            self._collect(task_id, pending, batch)

        batch.missing.extend(pending.values())
        return batch

    def _collect(self, task_id: str, pending: dict[str, str], batch: SerpBatch) -> None:
        key = pending[task_id]
        try:
            status, result = self.get(task_id)
        except DataForSeoError as exc:
            log.warning("task_get %s falhou: %s", task_id, exc)
            return
        if status == "pending":
            return
        del pending[task_id]
        if status == "ok":
            batch.results.append(parse_result(key, result or {}))
        else:
            batch.errors[key] = status


def parse_result(key: str, result: dict[str, Any]) -> SerpResult:
    """Converte o `result[0]` do task_get/advanced em SerpResult."""
    organic: list[OrganicResult] = []
    for item in result.get("items") or []:
        if item.get("type") != "organic":
            continue
        organic.append(
            OrganicResult(
                rank_group=int(item.get("rank_group") or 0),
                rank_absolute=int(item.get("rank_absolute") or 0),
                domain=item.get("domain") or "",
                url=item.get("url") or "",
            )
        )
    organic.sort(key=lambda o: o.rank_group)
    features = sorted({t for t in (result.get("item_types") or []) if t != "organic"})
    return SerpResult(key=key, organic=organic, features=features)
