"""Compare the TLS fingerprint of python-requests with curl_cffi's browser impersonation.

    python examples/fingerprint_compare.py

Uses tls.browserleaks.com, which echoes back the JA3/JA4 and HTTP/2 (Akamai)
fingerprint it saw. Anti-bot vendors match these hashes against known browsers,
so a plain requests call is flagged before a single header is even looked at.
"""
import requests

from stealth_http import StealthClient

ECHO_URL = "https://tls.browserleaks.com/json"
FIELDS = ["ja3n_hash", "ja4", "akamai_hash", "user_agent"]


def show(label, data):
    print(f"\n== {label}")
    for key in FIELDS:
        value = data.get(key) or "-"
        print(f"  {key:<12} {value[:90]}")


def main():
    plain = requests.get(ECHO_URL, timeout=20).json()
    show("python-requests", plain)

    for profile in ["chrome", "safari17_0"]:
        with StealthClient(profiles=[profile]) as client:
            show(f"curl_cffi impersonate={profile}", client.get(ECHO_URL).json())


if __name__ == "__main__":
    main()
