# stealth-http-client

A small HTTP client for scraping sites that sit behind bot protection.

Most "blocked" scrapers aren't blocked because of their headers. They're blocked at the TLS handshake: `python-requests` sends an OpenSSL ClientHello that no real browser sends, and services like Cloudflare, Akamai and DataDome fingerprint it (JA3/JA4, HTTP/2 settings) before they even look at the User-Agent. This client wraps [curl_cffi](https://github.com/lexiforest/curl_cffi) so requests carry a real Chrome/Safari fingerprint, and adds the boring-but-necessary parts around it:

- **TLS/HTTP2 impersonation**: Chrome, Edge and Safari profiles, with optional switching to a new profile when a request gets a 403
- **Proxy rotation**: round-robin pool that benches a proxy after repeated blocks and brings it back after a cooldown
- **Retries**: exponential backoff with jitter, honours `Retry-After`, retries 403/429/5xx and network errors
- **Token refresh**: pass a `token_provider` and an expired bearer token (401) is refreshed and the request replayed once
- **Per-host throttling** so you don't hammer a site

## Why it matters

Output of `examples/fingerprint_compare.py`:

```
== python-requests
  ja3n_hash    62fcc66dfa1611e219a93df2d1bb1b24
  ja4          t13d1812h1_85036bcba153_b26ce05bbdd6
  akamai_hash  -
  user_agent   python-requests/2.34.2

== curl_cffi impersonate=chrome
  ja3n_hash    8e19337e7524d2573be54efb2b0784c9
  ja4          t13d1516h2_8daaf6152771_806a8c22fdea
  akamai_hash  52d84b11737d980aef856699f885ca86
  user_agent   Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 ...
```

`requests` doesn't even speak HTTP/2 (`h1` in the JA4, no Akamai hash), which on its own is enough for most WAFs to flag it. The impersonated session matches what a real Chrome sends.

## Install

```bash
git clone https://github.com/AntoJohn000/stealth-http-client
cd stealth-http-client
pip install -e ".[dev]"
```

## Usage

```python
from stealth_http import StealthClient, ProxyPool

pool = ProxyPool.from_env()          # PROXY_LIST=http://user:pass@host:port,...

with StealthClient(proxy_pool=pool or None, rotate_profiles=True, min_interval=1.0) as client:
    resp = client.get("https://books.toscrape.com/")
    print(resp.status_code, len(resp.text))
```

Refreshing a bearer token when the API starts returning 401:

```python
def get_token(client):
    r = client.post("https://example.com/auth", json={"key": "..."})
    return r.json()["access_token"]

client = StealthClient(token_provider=get_token)
client.refresh_token()                  # first token
client.get("https://example.com/api/items")  # a 401 later triggers a refresh + retry
```

## Examples

| Script | What it does |
| --- | --- |
| `examples/fingerprint_compare.py` | Prints the JA3/JA4/HTTP2 fingerprint of `requests` vs impersonated browsers |
| `examples/books_crawler.py` | Crawls [books.toscrape.com](https://books.toscrape.com) (a practice site) with pagination and writes a CSV |

```bash
python examples/books_crawler.py --pages 3 --output books.csv
```

## Tests

```bash
pytest
```

The tests use a fake session, so they don't hit the network.

## Notes

Use this on sites you're allowed to scrape. Respect robots.txt and rate limits, and don't use it to get around access controls on accounts or data you don't have rights to.

## License

MIT
