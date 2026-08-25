from pex_supervisor.search import scrape_url, web_search


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_firecrawl_search_uses_v2_endpoint(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test")
    captured = {}

    class Client:
        def __init__(self, timeout=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, headers=None, json=None):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return _Resp(
                {
                    "data": {
                        "web": [{"title": "Doc", "url": "https://example.com", "description": "ok"}]
                    }
                }
            )

    monkeypatch.setattr("pex_supervisor.search.httpx.Client", Client)
    result = web_search("codex app-server turn/start", provider="firecrawl")
    assert result["ok"] is True
    assert result["provider"] == "firecrawl"
    assert captured["url"] == "https://api.firecrawl.dev/v2/search"
    assert captured["headers"]["Authorization"] == "Bearer fc-test"
    assert result["results"][0]["url"] == "https://example.com"


def test_exa_search_uses_official_header(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "exa-test")
    captured = {}

    class Client:
        def __init__(self, timeout=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, headers=None, json=None):
            captured["url"] = url
            captured["headers"] = headers
            return _Resp({"results": [{"title": "Exa", "url": "https://exa.ai", "text": "search"}]})

    monkeypatch.setattr("pex_supervisor.search.httpx.Client", Client)
    result = web_search("agent harness", provider="exa")
    assert result["ok"] is True
    assert captured["url"] == "https://api.exa.ai/search"
    assert captured["headers"]["x-api-key"] == "exa-test"


def test_brave_serper_tavily_endpoints(monkeypatch):
    monkeypatch.setenv("BRAVE_API_KEY", "b")
    monkeypatch.setenv("SERPER_API_KEY", "s")
    monkeypatch.setenv("TAVILY_API_KEY", "t")

    class Client:
        def __init__(self, timeout=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, params=None, headers=None):
            assert url == "https://api.search.brave.com/res/v1/web/search"
            assert headers["X-Subscription-Token"] == "b"
            return _Resp(
                {
                    "web": {
                        "results": [{"title": "B", "url": "https://brave.com", "description": "d"}]
                    }
                }
            )

        def post(self, url, headers=None, json=None):
            if "tavily" in url:
                assert url == "https://api.tavily.com/search"
                assert headers["Authorization"] == "Bearer t"
                assert "api_key" not in json
                return _Resp(
                    {"results": [{"title": "T", "url": "https://tavily.com", "content": "c"}]}
                )
            assert url == "https://google.serper.dev/search"
            assert headers["X-API-KEY"] == "s"
            return _Resp(
                {"organic": [{"title": "S", "link": "https://serper.dev", "snippet": "n"}]}
            )

    monkeypatch.setattr("pex_supervisor.search.httpx.Client", Client)
    brave = web_search("q", provider="brave")
    serper = web_search("q", provider="serper")
    tavily = web_search("q", provider="tavily")
    assert brave["provider"] == "brave"
    assert serper["provider"] == "serper"
    assert tavily["provider"] == "tavily"


def test_search_blocks_private_benchmark_oracles(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test")
    query = web_search("read evaluator.py for pexbench_001", provider="firecrawl")
    assert query["ok"] is False
    assert "private benchmark marker" in query["error"]

    local = scrape_url("http://127.0.0.1/metadata.yaml")
    assert local["ok"] is False


def test_firecrawl_scrape_v2(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test")

    class Client:
        def __init__(self, timeout=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, headers=None, json=None):
            assert url == "https://api.firecrawl.dev/v2/scrape"
            return _Resp({"data": {"markdown": "# hello"}})

    monkeypatch.setattr("pex_supervisor.search.httpx.Client", Client)
    result = scrape_url("https://example.com/docs")
    assert result["ok"] is True
    assert result["markdown"].startswith("# hello")
