"""Semantic Scholar Graph and Recommendations APIs."""

from __future__ import annotations

import os
import urllib.parse

from .. import keys, net, records
from . import Skipped

GRAPH = "https://api.semanticscholar.org/graph/v1"
RECS = "https://api.semanticscholar.org/recommendations/v1"
FIELDS = "title,authors,year,venue,publicationVenue,externalIds,abstract,citationCount,openAccessPdf,publicationTypes"


def _headers() -> dict:
    key = keys.get("s2")
    return {"x-api-key": key} if key else {}


def _source() -> str:
    return "s2" if keys.get("s2") else "s2-keyless"


def has_key() -> bool:
    return bool(keys.get("s2"))


def s2_id(kind: str, value: str) -> str | None:
    if kind == "doi":
        return "DOI:" + value
    if kind == "arxiv":
        return "ARXIV:" + value
    if kind == "dblp":
        return "DBLP:" + value
    if kind == "s2":
        return value
    return None


def _pv(p: dict) -> dict:
    pv = p.get("publicationVenue")
    return pv if isinstance(pv, dict) else {}


def _venue_type(p: dict) -> str | None:
    pv = _pv(p)
    venue = (pv.get("name") or p.get("venue") or "").lower()
    types = [t.lower() for t in (p.get("publicationTypes") or [])]
    if "workshop" in venue:
        return "workshop"
    if pv.get("type") == "conference" or "conference" in types:
        return "conference"
    if pv.get("type") == "journal" or "journalarticle" in types:
        if "arxiv" in venue:
            return "preprint"
        return "journal"
    if not venue or "arxiv" in venue:
        return "preprint"
    return "other"


def to_record(p: dict) -> dict | None:
    if not p or not p.get("paperId"):
        return None
    ext = p.get("externalIds") or {}
    pv = _pv(p)
    venue = pv.get("name") or p.get("venue") or None
    if venue and venue.lower() in ("arxiv.org", "arxiv"):
        venue = "arXiv"
    oa = (p.get("openAccessPdf") or {}).get("url") or None
    return records.make(
        "s2",
        {"s2": p["paperId"], "doi": ext.get("DOI"), "arxiv": ext.get("ArXiv"), "dblp": ext.get("DBLP")},
        p.get("title"),
        authors=[a.get("name") for a in p.get("authors") or []],
        year=p.get("year"),
        venue=venue,
        venue_type=_venue_type(p),
        abstract=p.get("abstract"),
        citation_count=p.get("citationCount"),
        fulltext_url=oa,
    )


def search(query: str, limit: int = 10, year_from: int | None = None, year_to: int | None = None):
    if not has_key() and not os.environ.get("NOVELTY_CHECK_S2_KEYLESS"):
        raise Skipped("no API key, reduced mode")
    params = {"query": query.replace("-", " "), "limit": max(1, min(limit, 100)), "fields": FIELDS}
    if year_from or year_to:
        params["year"] = "%s-%s" % (year_from or "", year_to or "")
    data = net.get_json(_source(), GRAPH + "/paper/search", params=params, headers=_headers())
    recs = [r for r in (to_record(p) for p in data.get("data") or []) if r]
    return recs, data.get("total")


def get(kind: str, value: str) -> dict | None:
    sid = s2_id(kind, value)
    if not sid:
        return None
    url = GRAPH + "/paper/" + urllib.parse.quote(sid, safe=":/")
    data = net.get_json(_source(), url, params={"fields": FIELDS}, headers=_headers(), ok_404=True)
    return to_record(data) if data else None


def expand(kind: str, value: str, mode: str, limit: int = 30) -> list[dict]:
    sid = s2_id(kind, value)
    if not sid:
        raise net.SourceError("s2: cannot look up %s:%s" % (kind, value))
    quoted = urllib.parse.quote(sid, safe=":/")
    if mode == "recommend":
        params = {"fields": FIELDS, "limit": max(1, min(limit, 500)), "from": "all-cs"}
        data = net.get_json(_source(), RECS + "/papers/forpaper/" + quoted, params=params, headers=_headers())
        papers = data.get("recommendedPapers") or []
    else:
        endpoint = "citations" if mode == "citations" else "references"
        params = {"fields": FIELDS, "limit": max(1, min(limit, 1000))}
        data = net.get_json(_source(), "%s/paper/%s/%s" % (GRAPH, quoted, endpoint), params=params, headers=_headers())
        inner = "citingPaper" if mode == "citations" else "citedPaper"
        papers = [row.get(inner) for row in data.get("data") or []]
    return [r for r in (to_record(p) for p in papers if p) if r]
