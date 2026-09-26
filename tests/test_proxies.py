from stealth_http import ProxyPool


def test_round_robin_covers_all_proxies():
    pool = ProxyPool(["http://a:1", "http://b:1", "http://c:1"])
    seen = {pool.get().url for _ in range(3)}
    assert seen == {"http://a:1", "http://b:1", "http://c:1"}


def test_proxy_benched_after_repeated_failures():
    pool = ProxyPool(["http://a:1"], max_failures=2, cooldown=60)
    proxy = pool.get()
    pool.mark_bad(proxy)
    assert pool.get() is proxy
    pool.mark_bad(proxy)
    assert pool.get() is None


def test_success_resets_failure_count():
    pool = ProxyPool(["http://a:1"], max_failures=2)
    proxy = pool.get()
    pool.mark_bad(proxy)
    pool.mark_ok(proxy)
    pool.mark_bad(proxy)
    assert pool.get() is proxy


def test_from_env(monkeypatch):
    monkeypatch.setenv("PROXY_LIST", "http://a:1, http://b:2 ,")
    assert len(ProxyPool.from_env()) == 2


def test_empty_pool_is_falsy():
    assert not ProxyPool([])
