"""OpenAlex works API. Keyword searches cost $0.001 each, single-record lookups are free."""

from __future__ import annotations

import re

from .. import ids, keys, net, records

BASE = "https://api.openalex.org"
SELECT = (
    "id,doi,display_name,publication_year,type,authorships,primary_location,"
    "cited_by_count,best_oa_location,abstract_inverted_index"
)
# Physical Sciences: computer science, engineering, mathematics and neighbours.
DEFAULT_DOMAIN_FILTER = "primary_topic.domain.id:domains/3"


def _params(extra: dict) -> dict:
    params = dict(extra)
    key = keys.get("openalex")
    if key:
        params["api_key"] = key
    return params


def rebuild_abstract(inverted: dict | None) -> str | None:
    if not inverted:
        return None
    positions = []
    for word, idxs in inverted.items():
        for i in idxs:
            positions.append((i, word))
    positions.sort()
    return " ".join(w for _, w in positions) or None


def _venue_type(w: dict, venue: str | None, source_type: str | None) -> str | None:
    wtype = (w.get("type") or "").lower()
    v = (venue or "").lower()
    if wtype == "preprint" or source_type == "repository" or "arxiv" in v:
        return "preprint"
    if wtype == "report":
        return "report"
    if wtype == "dissertation":
        return "thesis"
    if "workshop" in v:
        return "workshop"
    if source_type == "conference" or "conference" in wtype or "proceedings" in wtype:
        return "conference"
    if source_type == "journal":
        return "journal"
    return "other" if wtype else None


def to_record(w: dict) -> dict | None:
    if not w or not w.get("id"):
        return None
    wid = w["id"].rsplit("/", 1)[-1]
    pl = w.get("primary_location") or {}
    src = pl.get("source") or {}
    venue = src.get("display_name")
    arxiv = None
    for loc in (pl, w.get("best_oa_location") or {}):
        for field in ("landing_page_url", "pdf_url"):
            m = re.search(r"arxiv\.org/(?:abs|pdf)/([^\s?#]+?)(?:\.pdf)?$", (loc or {}).get(field) or "")
            if m and not arxiv:
                arxiv = ids.norm_arxiv(m.group(1))
    best = w.get("best_oa_location") or {}
    if venue and "arxiv" in venue.lower():
        venue = "arXiv"
    return records.make(
        "openalex",
        {"openalex": wid, "doi": w.get("doi"), "arxiv": arxiv},
        w.get("display_name"),
        authors=[(a.get("author") or {}).get("display_name") for a in w.get("authorships") or []],
        year=w.get("publication_year"),
        venue=venue,
        venue_type=_venue_type(w, venue, src.get("type")),
        abstract=rebuild_abstract(w.get("abstract_inverted_index")),
        citation_count=w.get("cited_by_count"),
        fulltext_url=best.get("pdf_url"),
    )


def search(query: str, limit: int = 10, year_from: int | None = None, year_to: int | None = None, any_field: bool = False):
    filters = [] if any_field else [DEFAULT_DOMAIN_FILTER]
    if year_from:
        filters.append("from_publication_date:%d-01-01" % year_from)
    if year_to:
        filters.append("to_publication_date:%d-12-31" % year_to)
    params = {"search": query, "per-page": max(1, min(limit, 100)), "select": SELECT}
    if filters:
        params["filter"] = ",".join(filters)
    data = net.get_json("openalex", BASE + "/works", params=_params(params))
    recs = [r for r in (to_record(w) for w in data.get("results") or []) if r]
    return recs, (data.get("meta") or {}).get("count")


def _work_path(kind: str, value: str) -> str | None:
    if kind == "openalex":
        return value
    if kind == "doi":
        return "doi:" + value
    if kind == "arxiv":
        return "doi:10.48550/arxiv." + value
    return None


def get(kind: str, value: str) -> dict | None:
    path = _work_path(kind, value)
    if not path:
        return None
    data = net.get_json("openalex", BASE + "/works/" + path, params=_params({"select": SELECT}), ok_404=True)
    return to_record(data) if data else None


def expand(kind: str, value: str, mode: str, limit: int = 30, query: str | None = None) -> list[dict]:
    """Citing or cited works. With `query`, only citing works that also match the keywords."""
    if mode == "recommend":
        raise net.SourceError("openalex: no recommendations; use s2")
    path = _work_path(kind, value)
    if not path:
        raise net.SourceError("openalex: cannot look up %s:%s" % (kind, value))
    work = net.get_json("openalex", BASE + "/works/" + path, params=_params({"select": "id,referenced_works"}), ok_404=True)
    if not work:
        return []
    wid = work["id"].rsplit("/", 1)[-1]
    if mode == "citations":
        params = {"filter": "cites:" + wid, "per-page": max(1, min(limit, 100)), "select": SELECT}
        if query:
            params["search"] = query
        else:
            params["sort"] = "cited_by_count:desc"
    else:
        refs = [r.rsplit("/", 1)[-1] for r in work.get("referenced_works") or []][: min(limit, 100)]
        if not refs:
            return []
        params = {"filter": "openalex_id:" + "|".join(refs), "per-page": len(refs), "select": SELECT}
    data = net.get_json("openalex", BASE + "/works", params=_params(params))
    return [r for r in (to_record(w) for w in data.get("results") or []) if r]


def request_key(email: str) -> dict:
    """Ask OpenAlex to email a free API key to `email` (the user must click the link)."""
    import json

    body = json.dumps({"email": email}).encode()
    resp = net.fetch(
        "openalex",
        BASE + "/api-keys",
        method="POST",
        data=body,
        headers={"Content-Type": "application/json"},
        cache=False,
        retries=1,
    )
    try:
        payload = resp.json()
    except ValueError:
        payload = {"raw": resp.text[:500]}
    return {"status": resp.status, "response": payload}
