"""HTTP with a disk cache, cross-process rate limiting and retries.

Several search subagents call the script at the same time, so pacing has to work across
processes: each source has a lock file plus a "next free slot" timestamp in the cache directory.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

from . import USER_AGENT, util

# Minimum seconds between two requests to the same source, across all processes.
INTERVALS = {
    "s2": 1.05,  # 1 request/s with a key
    "s2-keyless": 1.5,  # shared public pool
    "openalex": 0.15,  # well under 10 requests/s
    "arxiv": 3.1,  # arXiv API terms ask for one request every 3 seconds
    "arxiv-web": 1.0,
    "dblp": 0.5,
    "openreview": 1.0,
    "doi": 0.3,
    "fulltext": 1.0,
}
# Retries for answers that mean "try again later" (429, 5xx): (retries, first wait, longest wait).
# Semantic Scholar answers 429 at busy times even far below a key's 1 request/s: on 2026-11-05
# about half of all keyed searches failed that way although they were 2 to 5 seconds apart.
# Spacing doesn't help there, retrying does, so it gets more and shorter retries.
RETRY_POLICY = {
    "s2": (6, 1.5, 15.0),
    "s2-keyless": (4, 2.0, 20.0),
}
DEFAULT_RETRY = (3, 2.0, 60.0)
CACHE_TTL = 7 * 24 * 3600
RETRY_STATUSES = (429, 500, 502, 503, 504)
REDACT_PARAMS = ("api_key",)
REDACT_HEADERS = ("x-api-key",)

_no_cache = bool(os.environ.get("NOVELTY_CHECK_NO_CACHE"))


class SourceError(Exception):
    """A source could not answer. `kind` is 'network', 'http' or 'budget'."""

    def __init__(self, message: str, kind: str = "http", status: int | None = None):
        super().__init__(message)
        self.kind = kind
        self.status = status


class Response:
    def __init__(self, status: int, text: str, cached: bool = False, headers: dict | None = None):
        self.status = status
        self.text = text
        self.cached = cached
        self.headers = headers or {}

    def json(self):
        return json.loads(self.text)


def disable_cache() -> None:
    global _no_cache
    _no_cache = True


def _cache_key(method: str, url: str, headers: dict, data: bytes | None) -> str:
    parts = urllib.parse.urlsplit(url)
    query = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True) if k not in REDACT_PARAMS]
    clean_url = urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(sorted(query))))
    hdrs = sorted((k.lower(), v) for k, v in headers.items() if k.lower() not in REDACT_HEADERS)
    h = hashlib.sha256()
    h.update(method.encode())
    h.update(clean_url.encode())
    h.update(json.dumps(hdrs).encode())
    if data:
        h.update(data)
    return h.hexdigest()


def _cache_path(key: str) -> str:
    return os.path.join(util.cache_dir(), "http", key[:2], key + ".json")


def _cache_read(key: str) -> Response | None:
    if _no_cache:
        return None
    path = _cache_path(key)
    try:
        if time.time() - os.path.getmtime(path) > CACHE_TTL:
            return None
        with open(path, encoding="utf-8") as f:
            entry = json.load(f)
        return Response(entry["status"], entry["text"], cached=True)
    except (OSError, ValueError, KeyError):
        return None


def _cache_write(key: str, resp: Response) -> None:
    path = _cache_path(key)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = "%s.%d.tmp" % (path, os.getpid())
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"status": resp.status, "text": resp.text, "time": util.now_iso()}, f)
        os.replace(tmp, path)
    except OSError:
        pass


def throttle(source: str) -> None:
    """Wait for this process's turn to call `source`."""
    interval = INTERVALS.get(source, 1.0)
    lock_dir = os.path.join(util.cache_dir(), "locks")
    stamp = os.path.join(lock_dir, source + ".next")
    with util.locked(os.path.join(lock_dir, source + ".lock")):
        try:
            with open(stamp, encoding="utf-8") as f:
                next_free = float(f.read().strip() or 0)
        except (OSError, ValueError):
            next_free = 0.0
        now = time.time()
        slot = max(now, next_free)
        with open(stamp, "w", encoding="utf-8") as f:
            f.write("%.3f" % (slot + interval))
    delay = slot - now
    if delay > 0:
        time.sleep(delay)


def _build_url(url: str, params: dict | None) -> str:
    if not params:
        return url
    clean = {k: v for k, v in params.items() if v is not None and v != ""}
    sep = "&" if "?" in url else "?"
    return url + sep + urllib.parse.urlencode(clean)


def _retry_after(headers, attempt: int, source: str = "") -> float:
    """Seconds to wait before retry number `attempt + 1`: the server's Retry-After, else backoff."""
    value = headers.get("Retry-After") if headers else None
    if value:
        try:
            return min(60.0, max(1.0, float(value)))
        except ValueError:
            pass
    _, first, longest = RETRY_POLICY.get(source, DEFAULT_RETRY)
    return min(longest, first * 1.6**attempt + random.uniform(0, first / 2))


def fetch(
    source: str,
    url: str,
    params: dict | None = None,
    headers: dict | None = None,
    method: str = "GET",
    data: bytes | None = None,
    cache: bool = True,
    retries: int | None = None,
    timeout: float = 30.0,
) -> Response:
    """Fetch a URL as text. Returns any HTTP status; raises SourceError only when no answer came back.

    `retries` defaults to the source's entry in RETRY_POLICY.
    """
    if retries is None:
        retries = RETRY_POLICY.get(source, DEFAULT_RETRY)[0]
    full_url = _build_url(url, params)
    hdrs = {"User-Agent": USER_AGENT}
    hdrs.update(headers or {})
    key = _cache_key(method, full_url, hdrs, data)
    use_cache = cache and method == "GET"
    if use_cache:
        hit = _cache_read(key)
        if hit is not None:
            return hit

    last_error = "no attempt made"
    for attempt in range(retries + 1):
        throttle(source)
        req = urllib.request.Request(full_url, data=data, headers=hdrs, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                text = r.read().decode("utf-8", errors="replace")
                resp = Response(r.status, text, headers=dict(r.headers))
            if use_cache and resp.status == 200:
                _cache_write(key, resp)
            return resp
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace") if e.fp else ""
            if e.code == 429 and _is_budget_error(body):
                raise SourceError(
                    "%s: daily budget exhausted or plan required: %s" % (source, _snippet(body)), "budget", 429
                ) from None
            if e.code in RETRY_STATUSES and attempt < retries:
                last_error = "HTTP %d" % e.code
                time.sleep(_retry_after(e.headers, attempt, source))
                continue
            return Response(e.code, body, headers=dict(e.headers or {}))
        except (urllib.error.URLError, socket.timeout, ConnectionError, TimeoutError) as e:
            reason = getattr(e, "reason", e)
            last_error = str(reason)
            if attempt < retries:
                time.sleep(_retry_after(None, attempt, source))
                continue
            raise SourceError("%s: no answer (%s)" % (source, last_error), "network") from e
    raise SourceError("%s: gave up after %d retries (%s)" % (source, retries, last_error))


def _is_budget_error(body: str) -> bool:
    low = body.lower()
    return "budget" in low or "plan upgrade" in low


def _snippet(text: str, n: int = 200) -> str:
    return util.norm_space(text)[:n]


def get_json(source: str, url: str, params: dict | None = None, headers: dict | None = None, ok_404: bool = False, **kw):
    """GET JSON. Returns None on 404 when ok_404 is set; raises SourceError on other failures."""
    resp = fetch(source, url, params=params, headers=headers, **kw)
    if resp.status == 404 and ok_404:
        return None
    if resp.status != 200:
        raise SourceError("%s: HTTP %d: %s" % (source, resp.status, _snippet(resp.text)), "http", resp.status)
    try:
        return resp.json()
    except ValueError:
        raise SourceError("%s: answer was not JSON: %s" % (source, _snippet(resp.text))) from None


def download(source: str, url: str, dest: str, max_bytes: int = 40 * 1024 * 1024, timeout: float = 60.0) -> str:
    """Download a binary file (no cache). Returns the content type."""
    throttle(source)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            ctype = r.headers.get("Content-Type", "")
            total = 0
            with open(dest, "wb") as f:
                while True:
                    chunk = r.read(65536)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        raise SourceError("%s: file larger than %d MB" % (source, max_bytes // 1048576))
                    f.write(chunk)
            return ctype
    except urllib.error.HTTPError as e:
        raise SourceError("%s: HTTP %d for %s" % (source, e.code, url), "http", e.code) from e
    except (urllib.error.URLError, socket.timeout, ConnectionError, TimeoutError) as e:
        raise SourceError("%s: no answer (%s)" % (source, getattr(e, "reason", e)), "network") from e
