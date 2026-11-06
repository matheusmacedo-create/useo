import json
from pathlib import Path

import httpx

from useo.domains import belongs_to, normalize_domain
from useo.serp import SerpQuery
from useo.serp.dataforseo import DataForSeoProvider, parse_result
from useo.settings import DataForSeoSettings

FIX = Path(__file__).parent / "fixtures"


def load_fixture():
    return json.loads((FIX / "task_get_advanced.json").read_text())


def test_normalize_domain():
    assert normalize_domain("https://www.Unicopag.com.br/x?y=1") == "unicopag.com.br"
    assert normalize_domain("www.unicopag.com.br") == "unicopag.com.br"
    assert normalize_domain("unicopag.com.br:443/") == "unicopag.com.br"


def test_belongs_to():
    assert belongs_to("blog.unicopag.com.br", "unicopag.com.br")
    assert belongs_to("https://www.unicopag.com.br/a", "https://unicopag.com.br")
    assert not belongs_to("notunicopag.com.br", "unicopag.com.br")
    assert not belongs_to(None, "unicopag.com.br")


def test_parse_result_keeps_only_organic_sorted():
    result = load_fixture()["tasks"][0]["result"][0]
    serp = parse_result("KW-1", result)
    assert [o.rank_group for o in serp.organic] == [1, 2, 3, 4]
    assert serp.organic[2].domain == "www.unicopag.com.br"
    assert serp.features == ["paid", "people_also_ask", "related_searches"]


def make_transport(task_get_body):
    calls = {"post": 0, "ready": 0, "get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/task_post"):
            calls["post"] += 1
            payload = json.loads(request.content)
            assert payload[0]["location_code"] == 2076
            assert payload[0]["os"] == "windows"
            assert payload[1]["os"] == "android"
            tasks = [
                {
                    "id": f"T{i}",
                    "status_code": 20100,
                    "status_message": "Task Created.",
                    "cost": 0.0006,
                    "data": {"tag": t["tag"]},
                }
                for i, t in enumerate(payload)
            ]
            return httpx.Response(200, json={"status_code": 20000, "tasks": tasks})
        if path.endswith("/tasks_ready"):
            calls["ready"] += 1
            # 1ª chamada: só T0 pronto; T1 é coletado na tentativa final direta.
            return httpx.Response(
                200,
                json={"status_code": 20000, "tasks": [{"result": [{"id": "T0"}, {"id": "X"}]}]},
            )
        if "/task_get/advanced/" in path:
            calls["get"] += 1
            return httpx.Response(200, json=task_get_body)
        raise AssertionError(path)

    return httpx.MockTransport(handler), calls


def test_provider_fetch_flow():
    transport, calls = make_transport(load_fixture())
    t = [0.0]
    provider = DataForSeoProvider(
        DataForSeoSettings("l", "p"),
        client=httpx.Client(transport=transport),
        timeout_s=60,
        poll_every_s=30,
        sleep=lambda s: t.__setitem__(0, t[0] + s),
        clock=lambda: t[0],
    )
    batch = provider.fetch(
        [SerpQuery("KW-1", "gateway de pagamento"), SerpQuery("KW-2", "pix", device="mobile")]
    )
    assert calls["post"] == 1
    assert round(batch.cost_usd, 6) == 0.0012
    assert len(batch.results) == 2
    assert batch.missing == [] and batch.errors == {}


def test_provider_reports_missing_when_still_queued():
    queued = {
        "status_code": 20000,
        "tasks": [{"status_code": 40602, "status_message": "Task In Queue."}],
    }
    transport, _ = make_transport(queued)
    t = [0.0]
    provider = DataForSeoProvider(
        DataForSeoSettings("l", "p"),
        client=httpx.Client(transport=transport),
        timeout_s=60,
        sleep=lambda s: t.__setitem__(0, t[0] + s),
        clock=lambda: t[0],
    )
    batch = provider.fetch([SerpQuery("A", "a"), SerpQuery("B", "b", device="mobile")])
    assert batch.results == []
    assert sorted(batch.missing) == ["A", "B"]
