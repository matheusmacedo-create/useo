import json

import httpx
import pytest

from useo.db import Database, DatabaseError, in_filter
from useo.settings import SupabaseSettings


def make_db(handler):
    return Database(
        SupabaseSettings("https://x.supabase.co", "svc"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_select_paginates_and_sends_auth():
    seen = []

    def handler(req: httpx.Request):
        assert req.headers["apikey"] == "svc"
        assert req.headers["authorization"] == "Bearer svc"
        assert req.url.path == "/rest/v1/keywords"
        seen.append(dict(req.url.params))
        off = int(req.url.params["offset"])
        return httpx.Response(200, json=[{"i": i} for i in range(off, min(off + 2, 5))])

    rows = make_db(handler).select("keywords", filters={"ativo": "eq.true"}, page_size=2)
    assert [r["i"] for r in rows] == [0, 1, 2, 3, 4]
    assert [p["offset"] for p in seen] == ["0", "2", "4"]
    assert seen[0]["ativo"] == "eq.true"


def test_upsert_uses_on_conflict_and_merge():
    def handler(req: httpx.Request):
        assert req.method == "POST"
        assert req.url.params["on_conflict"] == "keyword_id,data"
        assert "merge-duplicates" in req.headers["prefer"]
        return httpx.Response(201, json=json.loads(req.content))

    out = make_db(handler).upsert("rank_checks", [{"a": 1}], on_conflict="keyword_id,data")
    assert out == [{"a": 1}]


def test_errors_and_guards():
    db = make_db(lambda req: httpx.Response(401, text="bad key"))
    with pytest.raises(DatabaseError, match="401"):
        db.select("sites")
    with pytest.raises(ValueError):
        db.update("sites", {"ativo": False}, filters={})


def test_in_filter_quotes():
    assert in_filter(["a", "b"]) == "in.(a,b)"
    assert in_filter(["a b"]) == 'in.("a b")'
