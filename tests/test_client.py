import pytest

from stealth_http import BlockedError, ProxyPool, StealthClient
from stealth_http import client as client_module


class FakeResponse:
    def __init__(self, status_code, headers=None):
        self.status_code = status_code
        self.headers = headers or {}


class FakeSession:
    def __init__(self, statuses):
        self.statuses = list(statuses)
        self.calls = []

    def request(self, method, url, headers=None, proxies=None, **kwargs):
        self.calls.append({"headers": headers, "proxies": proxies})
        return FakeResponse(self.statuses.pop(0))

    def close(self):
        pass


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(client_module.time, "sleep", lambda s: None)


def make_client(statuses, **kwargs):
    client = StealthClient(**kwargs)
    client.session = FakeSession(statuses)
    return client


def test_returns_first_good_response():
    client = make_client([200])
    assert client.get("https://example.com").status_code == 200
    assert len(client.session.calls) == 1


def test_retries_on_block_then_succeeds():
    client = make_client([429, 503, 200], max_retries=3)
    assert client.get("https://example.com").status_code == 200
    assert len(client.session.calls) == 3


def test_gives_up_after_max_retries():
    client = make_client([403] * 3, max_retries=2)
    with pytest.raises(BlockedError) as err:
        client.get("https://example.com")
    assert err.value.status == 403


def test_404_is_not_retried():
    client = make_client([404])
    assert client.get("https://example.com").status_code == 404


def test_refreshes_token_on_401():
    tokens = iter(["fresh-token"])
    client = make_client([401, 200], token_provider=lambda c: next(tokens))
    client.get("https://example.com/api")
    assert client.session.calls[-1]["headers"]["Authorization"] == "Bearer fresh-token"


def test_blocked_proxy_gets_benched():
    pool = ProxyPool(["http://p1:8000"], max_failures=1, cooldown=60)
    client = make_client([403, 200], proxy_pool=pool, max_retries=1)

    assert client.get("https://example.com").status_code == 200
    first, second = client.session.calls
    assert first["proxies"]["https"] == "http://p1:8000"
    assert second["proxies"] is None  # only proxy is on cooldown
    assert pool.get() is None
