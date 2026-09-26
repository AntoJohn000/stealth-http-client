import logging
import random
import threading
import time
from urllib.parse import urlsplit

from curl_cffi import requests as curl_requests
from curl_cffi.requests.exceptions import RequestException

log = logging.getLogger(__name__)

# Browser profiles curl_cffi can impersonate. The TLS handshake (JA3/JA4),
# HTTP/2 settings and header order all match the real browser.
DEFAULT_PROFILES = ["chrome", "chrome131", "chrome124", "edge101", "safari17_0"]

RETRY_STATUSES = {403, 408, 425, 429, 500, 502, 503, 504}


class BlockedError(Exception):
    """Raised when every retry came back blocked or failed."""

    def __init__(self, url, status=None, reason=None):
        self.url = url
        self.status = status
        super().__init__(f"{url} failed after retries (status={status}, reason={reason})")


class StealthClient:
    """HTTP client that looks like a real browser at the TLS layer.

    - curl_cffi impersonation instead of python-requests' OpenSSL fingerprint
    - optional proxy rotation through a ProxyPool
    - retries with exponential backoff + jitter on blocks and 5xx
    - per-host throttling
    - bearer token refresh on 401 via a `token_provider` callable
    """

    def __init__(self, proxy_pool=None, profiles=None, rotate_profiles=False,
                 max_retries=4, backoff=1.5, min_interval=0.0, timeout=30,
                 token_provider=None, headers=None):
        self.proxy_pool = proxy_pool
        self.profiles = profiles or DEFAULT_PROFILES
        self.rotate_profiles = rotate_profiles
        self.max_retries = max_retries
        self.backoff = backoff
        self.min_interval = min_interval
        self.timeout = timeout
        self.token_provider = token_provider
        self.token = None

        self.profile = self.profiles[0]
        self.session = self._new_session()
        self.default_headers = headers or {}

        self._last_hit = {}
        self._throttle_lock = threading.Lock()

    def _new_session(self):
        return curl_requests.Session(impersonate=self.profile)

    def _next_profile(self):
        """Switch to a different browser profile and start a fresh session (new cookies)."""
        choices = [p for p in self.profiles if p != self.profile] or self.profiles
        self.profile = random.choice(choices)
        self.session.close()
        self.session = self._new_session()
        log.debug("switched impersonation profile to %s", self.profile)

    def _throttle(self, url):
        if not self.min_interval:
            return
        host = urlsplit(url).hostname
        with self._throttle_lock:
            wait = self._last_hit.get(host, 0) + self.min_interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last_hit[host] = time.monotonic()

    def _sleep_before_retry(self, attempt, response=None):
        retry_after = response.headers.get("retry-after") if response is not None else None
        if retry_after and retry_after.isdigit():
            delay = int(retry_after)
        else:
            delay = self.backoff ** attempt + random.uniform(0, 1)
        log.info("retrying in %.1fs", delay)
        time.sleep(delay)

    def refresh_token(self):
        if not self.token_provider:
            return False
        self.token = self.token_provider(self)
        return bool(self.token)

    def request(self, method, url, headers=None, **kwargs):
        last_status, last_reason = None, None
        token_refreshed = False

        for attempt in range(self.max_retries + 1):
            proxy = self.proxy_pool.get() if self.proxy_pool else None
            merged = {**self.default_headers, **(headers or {})}
            if self.token:
                merged["Authorization"] = f"Bearer {self.token}"

            self._throttle(url)
            try:
                resp = self.session.request(
                    method, url, headers=merged, timeout=self.timeout,
                    proxies={"http": proxy.url, "https": proxy.url} if proxy else None,
                    **kwargs,
                )
            except RequestException as exc:
                log.warning("%s %s -> network error: %s", method, url, exc)
                last_reason = str(exc)
                if self.proxy_pool:
                    self.proxy_pool.mark_bad(proxy)
                if attempt < self.max_retries:
                    self._sleep_before_retry(attempt)
                continue

            last_status = resp.status_code

            # expired token: refresh once and retry straight away
            if resp.status_code == 401 and self.token_provider and not token_refreshed:
                log.info("got 401, refreshing token")
                token_refreshed = self.refresh_token()
                if token_refreshed:
                    continue

            if resp.status_code in RETRY_STATUSES:
                log.warning("%s %s -> %s (attempt %d)", method, url, resp.status_code, attempt + 1)
                if self.proxy_pool and resp.status_code in (403, 429):
                    self.proxy_pool.mark_bad(proxy)
                if self.rotate_profiles and resp.status_code == 403:
                    self._next_profile()
                if attempt < self.max_retries:
                    self._sleep_before_retry(attempt, resp)
                continue

            if self.proxy_pool:
                self.proxy_pool.mark_ok(proxy)
            return resp

        raise BlockedError(url, status=last_status, reason=last_reason)

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)

    def close(self):
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
