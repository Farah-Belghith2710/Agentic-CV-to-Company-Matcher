"""Polite HTTP for job sources: one shared client, on-disk caching, per-host throttling."""
from __future__ import annotations

import threading
import time
from urllib.parse import urlparse

import httpx

from ..cache import cache, make_key
from ..config import settings

USER_AGENT = "cv-job-matcher/1.0 (personal portfolio project; respects rate limits)"

# Minimum seconds between two requests to the same host. Remotive allows at most 2 requests/minute.
MIN_INTERVAL = {"remotive.com": 35.0, "www.arbeitnow.com": 2.0}
DEFAULT_INTERVAL = 1.0

_last_call: dict[str, float] = {}
_lock = threading.Lock()
_client: httpx.Client | None = None


class SourceError(RuntimeError):
    pass


def _get_client() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(
            timeout=settings.http_timeout,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            follow_redirects=True,
        )
    return _client


def wait_seconds(url: str) -> float:
    host = urlparse(url).netloc
    gap = MIN_INTERVAL.get(host, DEFAULT_INTERVAL)
    with _lock:
        last = _last_call.get(host, 0.0)
    return max(0.0, last + gap - time.time())


def get_json(url: str, params: dict | None = None, ttl: float = 6 * 3600, allow_404: bool = False):
    """GET JSON with caching. Returns None for 404 when allow_404 is set."""
    key = make_key(url, params or {})
    hit = cache.get("http", key)
    if hit is not None:
        return hit["body"]
    host = urlparse(url).netloc
    delay = wait_seconds(url)
    if delay > 0:
        time.sleep(delay)
    with _lock:
        _last_call[host] = time.time()
    try:
        resp = _get_client().get(url, params=params)
    except httpx.HTTPError as exc:
        raise SourceError(f"Could not reach {host}: {exc.__class__.__name__}") from exc
    if resp.status_code == 404 and allow_404:
        cache.set("http", key, {"body": None}, ttl=ttl)
        return None
    if resp.status_code == 429:
        raise SourceError(f"{host} is rate-limiting requests (HTTP 429). Try again in a few minutes.")
    if resp.status_code >= 400:
        raise SourceError(f"{host} answered HTTP {resp.status_code}.")
    try:
        body = resp.json()
    except ValueError as exc:
        raise SourceError(f"{host} did not return JSON.") from exc
    cache.set("http", key, {"body": body}, ttl=ttl)
    return body
