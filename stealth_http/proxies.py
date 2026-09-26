import os
import random
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Proxy:
    url: str
    failures: int = 0
    banned_until: float = 0.0

    @property
    def available(self):
        return time.monotonic() >= self.banned_until


@dataclass
class ProxyPool:
    """Round-robin proxy pool that benches proxies after repeated failures.

    A proxy that fails `max_failures` times in a row is put on cooldown instead
    of being dropped, since residential exits usually come back after a while.
    """

    proxies: list = field(default_factory=list)
    max_failures: int = 3
    cooldown: float = 120.0

    def __post_init__(self):
        self.proxies = [p if isinstance(p, Proxy) else Proxy(p) for p in self.proxies]
        random.shuffle(self.proxies)
        self._index = 0
        self._lock = threading.Lock()

    @classmethod
    def from_env(cls, var="PROXY_LIST", **kwargs):
        """Comma separated list, e.g. PROXY_LIST=http://u:p@host1:8000,http://host2:8000"""
        raw = os.environ.get(var, "")
        return cls([p.strip() for p in raw.split(",") if p.strip()], **kwargs)

    @classmethod
    def from_file(cls, path, **kwargs):
        lines = Path(path).read_text().splitlines()
        return cls([ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")], **kwargs)

    def __len__(self):
        return len(self.proxies)

    def get(self):
        """Next usable proxy, or None if the pool is empty or everything is benched."""
        with self._lock:
            for _ in range(len(self.proxies)):
                proxy = self.proxies[self._index % len(self.proxies)]
                self._index += 1
                if proxy.available:
                    return proxy
        return None

    def mark_ok(self, proxy):
        if proxy:
            proxy.failures = 0

    def mark_bad(self, proxy):
        if not proxy:
            return
        with self._lock:
            proxy.failures += 1
            if proxy.failures >= self.max_failures:
                proxy.banned_until = time.monotonic() + self.cooldown
                proxy.failures = 0
