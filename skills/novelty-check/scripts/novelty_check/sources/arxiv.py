"""arXiv API (Atom XML). One request every 3 seconds, as arXiv asks."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from .. import ids, net, records, util

API = "https://export.arxiv.org/api/query"
NS = {
    "a": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
    "os": "http://a9.com/-/spec/opensearch/1.1/",
}
# CS plus the neighbouring categories where CS work often lands.
CATEGORIES = "(cat:cs.* OR cat:stat.ML OR cat:eess.*)"
FIELD_SYNTAX = re.compile(r"\b(ti|abs|au|all|cat|co|jr|rn|id|submittedDate):")


def build_query(query: str, year_from: int | None = None, year_to: int | None = None) -> str:
    """Turn short keywords into an arXiv query: every term must match, CS categories only.

    Quoted phrases stay phrases. A query that already uses arXiv field syntax is passed through.
    """
    if FIELD_SYNTAX.search(query):
        q = query
    else:
        parts = []
        for term in re.findall(r'"[^"]+"|\S+', query):
            if term.startswith('"'):
                parts.append("all:%s" % term)
                continue
            for word in re.split(r"[-/]", term):
                word = re.sub(r"[^\w*]", "", word)
                if word and word.lower() not in util.STOPWORDS:
                    parts.append("all:%s" % word)
        if not parts:
            raise net.SourceError("arxiv: the query has no usable words")
        q = "(%s) AND %s" % (" AND ".join(parts), CATEGORIES)
    if year_from or year_to:
        q += " AND submittedDate:[%s01010000 TO %s12312359]" % (year_from or 1991, year_to or 2099)
    return q


def _text(el, path: str) -> str | None:
    found = el.find(path, NS)
    return found.text if found is not None and found.text else None


def parse_feed(xml_text: str):
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise net.SourceError("arxiv: could not read the answer (%s)" % e) from e
    total = _text(root, "os:totalResults")
    recs = []
    for entry in root.findall("a:entry", NS):
        raw_id = _text(entry, "a:id") or ""
        if "api/errors" in raw_id:
            raise net.SourceError("arxiv: %s" % util.norm_space(_text(entry, "a:summary")))
        m = re.search(r"arxiv\.org/abs/(.+)$", raw_id)
        aid = ids.norm_arxiv(m.group(1)) if m else None
        if not aid:
            continue
        published = _text(entry, "a:published") or ""
        journal_ref = util.norm_space(_text(entry, "arxiv:journal_ref")) or None
        recs.append(
            records.make(
                "arxiv",
                {"arxiv": aid, "doi": _text(entry, "arxiv:doi")},
                _text(entry, "a:title"),
                authors=[_text(a, "a:name") for a in entry.findall("a:author", NS)],
                year=published[:4] or None,
                venue="arXiv",
                venue_type="preprint",
                abstract=_text(entry, "a:summary"),
                fulltext_url="https://arxiv.org/html/" + aid,
                journal_ref=journal_ref,
            )
        )
    return recs, int(total) if total and total.isdigit() else None


def search(query: str, limit: int = 10, year_from: int | None = None, year_to: int | None = None):
    params = {
        "search_query": build_query(query, year_from, year_to),
        "start": 0,
        "max_results": max(1, min(limit, 100)),
        "sortBy": "relevance",
    }
    resp = net.fetch("arxiv", API, params=params)
    if resp.status != 200:
        raise net.SourceError("arxiv: HTTP %d" % resp.status, "http", resp.status)
    return parse_feed(resp.text)


def get(kind: str, value: str) -> dict | None:
    if kind != "arxiv":
        return None
    resp = net.fetch("arxiv", API, params={"id_list": value, "max_results": 1})
    if resp.status != 200:
        raise net.SourceError("arxiv: HTTP %d" % resp.status, "http", resp.status)
    recs, _ = parse_feed(resp.text)
    return recs[0] if recs else None
