"""OpenReview API v2 search (ICLR, NeurIPS, TMLR and others, including unaccepted submissions).

Searching works without an account. Fetching a single note by ID currently answers with a bot
challenge, so OpenReview records are only known through search results kept in the run's store.
"""

from __future__ import annotations

import datetime
import re

from .. import net, records

API = "https://api2.openreview.net"
# OpenReview also holds copies of papers imported from DBLP, ORCID and author uploads. Only
# submissions to venues run on OpenReview add something the other sources lack.
IMPORTED_DOMAINS = ("DBLP.org", "OpenReview.net/Public_Article", "OpenReview.net/Archive")


def _value(content: dict, key: str):
    v = content.get(key)
    if isinstance(v, dict):
        return v.get("value")
    return v


def _status(venue: str) -> str | None:
    v = venue.lower()
    if "withdrawn" in v:
        return "withdrawn submission"
    if "desk rejected" in v or "rejected" in v:
        return "rejected"
    if v.startswith("submitted to") or "under review" in v or v.endswith("submission"):
        return "submitted, not accepted (yet)"
    return None


def _venue_type(venue: str, venueid: str) -> str:
    if _status(venue):
        return "submission"
    v = (venue + " " + venueid).lower()
    if "workshop" in v:
        return "workshop"
    if "tmlr" in v or "transactions" in v or "journal" in v:
        return "journal"
    return "conference"


def _year(note: dict, venue: str) -> int | None:
    m = re.search(r"\b(19|20)\d{2}\b", venue)
    if m:
        return int(m.group(0))
    for field in ("pdate", "odate", "cdate"):
        ms = note.get(field)
        if isinstance(ms, (int, float)) and ms > 0:
            return datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc).year
    return None


def to_record(note: dict) -> dict | None:
    content = note.get("content") or {}
    title = _value(content, "title")
    forum = note.get("forum") or note.get("id")
    if not title or not forum:
        return None
    venue = _value(content, "venue") or ""
    venueid = _value(content, "venueid") or ""
    domain = note.get("domain") or ""
    if domain in IMPORTED_DOMAINS or venueid.lower().startswith(("dblp.org/", "openreview.net/")):
        return None  # records imported into author profiles; the other sources cover them
    authors = _value(content, "authors") or []
    if not isinstance(authors, list):
        authors = []
    authors = [a if isinstance(a, str) else (a or {}).get("fullname") or (a or {}).get("name") for a in authors]
    if not authors and _status(venue):
        authors = ["(anonymous while under review)"]
    return records.make(
        "openreview",
        {"openreview": forum},
        title,
        authors=authors,
        year=_year(note, venue),
        venue=venue or None,
        venue_type=_venue_type(venue, venueid),
        abstract=_value(content, "abstract"),
        fulltext_url="https://openreview.net/pdf?id=" + forum,
        status=_status(venue),
        bibtex=_value(content, "_bibtex"),
    )


def search(query: str, limit: int = 10, year_from: int | None = None, year_to: int | None = None):
    fetch_n = min(100, limit * 3 if (year_from or year_to) else limit)
    params = {"term": query, "type": "terms", "content": "all", "source": "forum", "limit": max(1, fetch_n)}
    data = net.get_json("openreview", API + "/notes/search", params=params)
    recs = [r for r in (to_record(n) for n in data.get("notes") or []) if r]
    if year_from:
        recs = [r for r in recs if r.get("year") and r["year"] >= year_from]
    if year_to:
        recs = [r for r in recs if r.get("year") and r["year"] <= year_to]
    return recs[:limit], data.get("count")
