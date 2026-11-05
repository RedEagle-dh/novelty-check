"""Paper identifiers: parsing, normalisation, canonical IDs and record URLs.

Canonical ID strings look like ``doi:10.1145/3600006.3613165``, ``arxiv:2309.06180``,
``s2:<40 hex>``, ``openreview:<forum id>``, ``dblp:conf/sosp/KwonLZ0ZY0ZS23`` or
``openalex:W4387321091``.
"""

from __future__ import annotations

import re
import urllib.parse

KINDS = ("doi", "arxiv", "s2", "openreview", "dblp", "openalex")
# Which identifier names a work canonically when several are known.
PRIORITY = ("doi", "arxiv", "s2", "openreview", "dblp", "openalex")

ARXIV_NEW = re.compile(r"^(\d{4}\.\d{4,5})(v\d+)?$")
ARXIV_OLD = re.compile(r"^([a-z\-]+(?:\.[A-Za-z]{2})?/\d{7})(v\d+)?$", re.I)
S2_HEX = re.compile(r"^[0-9a-f]{40}$")
OPENALEX_W = re.compile(r"^W\d+$", re.I)


def norm_doi(doi: str) -> str | None:
    doi = urllib.parse.unquote(doi.strip())
    doi = re.sub(r"^(https?://)?(dx\.)?doi\.org/", "", doi, flags=re.I)
    doi = re.sub(r"^doi:\s*", "", doi, flags=re.I)
    doi = doi.strip().lower()
    return doi if doi.startswith("10.") and "/" in doi else None


def norm_arxiv(a: str) -> str | None:
    a = a.strip()
    a = re.sub(r"^arxiv:", "", a, flags=re.I)
    m = ARXIV_NEW.match(a)
    if m:
        return m.group(1)
    m = ARXIV_OLD.match(a)
    if m:
        return m.group(1)
    return None


def arxiv_from_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    m = re.match(r"^10\.48550/arxiv\.(.+)$", doi, re.I)
    return norm_arxiv(m.group(1)) if m else None


def normalize_pair(kind: str, value: str) -> tuple[str, str] | None:
    kind = kind.lower()
    value = value.strip()
    if not value:
        return None
    if kind == "doi":
        d = norm_doi(value)
        if not d:
            return None
        ax = arxiv_from_doi(d)
        return ("arxiv", ax) if ax else ("doi", d)
    if kind == "arxiv":
        a = norm_arxiv(value)
        return ("arxiv", a) if a else None
    if kind == "openalex":
        m = re.search(r"(W\d+)", value, re.I)
        return ("openalex", m.group(1).upper()) if m else None
    if kind == "s2":
        v = value.lower()
        return ("s2", v) if S2_HEX.match(v) else None
    if kind in ("dblp", "openreview"):
        return (kind, value)
    return None


_URLISH = re.compile(r"^(https?://|(www\.)?[a-z0-9.-]+\.[a-z]{2,}/)", re.I)


def parse_id(text: str) -> tuple[str, str] | None:
    """Parse a prefixed ID, a record URL or a bare DOI/arXiv/OpenAlex/S2 ID."""
    t = text.strip().strip("<>").rstrip(".,;")
    if t.endswith(")") and t.count("(") < t.count(")"):
        t = t[:-1]
    m = re.match(r"^(doi|arxiv|s2|openreview|dblp|openalex):(.+)$", t, re.I)
    if m:
        return normalize_pair(m.group(1), m.group(2))
    if _URLISH.match(t):
        return _parse_url(t)
    if t.startswith("10.") and "/" in t:
        return normalize_pair("doi", t)
    if ARXIV_NEW.match(t):
        return normalize_pair("arxiv", t)
    if OPENALEX_W.match(t):
        return ("openalex", t.upper())
    if S2_HEX.match(t.lower()):
        return ("s2", t.lower())
    return None


def _parse_url(t: str) -> tuple[str, str] | None:
    if not re.match(r"^https?://", t, re.I):
        t = "https://" + t
    u = urllib.parse.urlparse(t)
    host = u.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = u.path.lstrip("/")
    if host in ("doi.org", "dx.doi.org"):
        return normalize_pair("doi", path)
    if host in ("arxiv.org", "export.arxiv.org"):
        m = re.match(r"^(?:abs|pdf|html)/(.+?)(?:\.pdf)?/?$", path)
        return normalize_pair("arxiv", m.group(1)) if m else None
    if host == "openreview.net":
        q = urllib.parse.parse_qs(u.query)
        if q.get("id"):
            return ("openreview", q["id"][0])
        return None
    if host in ("dblp.org", "dblp.uni-trier.de", "dblp.dagstuhl.de"):
        m = re.match(r"^rec/(.+?)(?:\.html|\.bib|\.xml|\.ris)?$", path)
        return ("dblp", m.group(1)) if m else None
    if host in ("semanticscholar.org", "api.semanticscholar.org"):
        m = re.search(r"([0-9a-f]{40})", path)
        return ("s2", m.group(1)) if m else None
    if host in ("openalex.org", "api.openalex.org"):
        m = re.search(r"(W\d+)", path, re.I)
        return ("openalex", m.group(1).upper()) if m else None
    return None


def id_str(kind: str, value: str) -> str:
    return "%s:%s" % (kind, value)


def canonical(ids: dict) -> str | None:
    for kind in PRIORITY:
        if ids.get(kind):
            return id_str(kind, ids[kind])
    return None


def url_for(kind: str, value: str) -> str:
    if kind == "doi":
        return "https://doi.org/" + value
    if kind == "arxiv":
        return "https://arxiv.org/abs/" + value
    if kind == "s2":
        return "https://www.semanticscholar.org/paper/" + value
    if kind == "openreview":
        return "https://openreview.net/forum?id=" + value
    if kind == "dblp":
        return "https://dblp.org/rec/" + value
    if kind == "openalex":
        return "https://openalex.org/" + value
    raise ValueError(kind)


def record_url(ids: dict) -> str | None:
    for kind in PRIORITY:
        if ids.get(kind):
            return url_for(kind, ids[kind])
    return None


# Hosts whose record links count as scholarly evidence in a report.
SCHOLARLY_HOSTS = frozenset(
    {
        "doi.org",
        "dx.doi.org",
        "arxiv.org",
        "openreview.net",
        "dblp.org",
        "semanticscholar.org",
        "openalex.org",
    }
)
