"""DBLP through its SPARQL endpoint (QLever text search over titles).

The regular DBLP search API (dblp.org/search) answers scripts with a bot challenge, the SPARQL
endpoint does not. Text search matches titles only and requires every word to occur.
"""

from __future__ import annotations

import re

from .. import net, records, util

ENDPOINT = "https://sparql.dblp.org/sparql"
PREFIXES = """PREFIX dblp: <https://dblp.org/rdf/schema#>
PREFIX ql: <http://qlever.cs.uni-freiburg.de/builtin-functions/>
"""
FIELDS = """
  OPTIONAL { ?p dblp:yearOfPublication ?y }
  OPTIONAL { ?p dblp:publishedIn ?v }
  OPTIONAL { ?p dblp:doi ?d }
  OPTIONAL { ?p dblp:bibtexType ?ty }
  OPTIONAL { ?p dblp:hasSignature ?s . ?s dblp:signatureDblpName ?an . OPTIONAL { ?s dblp:signatureOrdinal ?ord } }
"""
SELECT = (
    "SELECT ?p (SAMPLE(?t) AS ?title) (SAMPLE(?y) AS ?year) (SAMPLE(?v) AS ?venue) (SAMPLE(?d) AS ?doi) "
    '(SAMPLE(?ty) AS ?type) (GROUP_CONCAT(DISTINCT CONCAT(STR(COALESCE(?ord, 0)), "~", ?an); separator="|") AS ?authors)'
)
INNER_LIMIT = 300


def words(query: str) -> list[str]:
    out = []
    for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9*]*", util.fold_ascii(query)):
        t = token.lower()
        if t not in util.STOPWORDS and len(t.rstrip("*")) >= 2:
            out.append(t)
    return out


def _escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def build_search(query: str) -> str:
    ws = words(query)
    if not ws:
        raise net.SourceError("dblp: the query has no usable words")
    return (
        PREFIXES
        + SELECT
        + " WHERE {\n { SELECT DISTINCT ?p ?t WHERE { ?p dblp:title ?t . ?text ql:contains-entity ?t . "
        + '?text ql:contains-word "%s" } LIMIT %d }\n' % (_escape(" ".join(ws)), INNER_LIMIT)
        + "  ?p dblp:title ?t ."
        + FIELDS
        + "} GROUP BY ?p"
    )


def build_get(key: str) -> str:
    return (
        PREFIXES
        + SELECT
        + " WHERE {\n VALUES ?p { <https://dblp.org/rec/%s> }\n ?p dblp:title ?t .%s} GROUP BY ?p" % (key, FIELDS)
    )


def _venue_type(type_uri: str, venue: str, key: str) -> str:
    t = type_uri.rsplit("#", 1)[-1].lower()
    v = venue.lower()
    if key.startswith("journals/corr/") or t == "informal":
        return "preprint"
    if "workshop" in v or re.search(r"@", venue):
        return "workshop"
    if t == "inproceedings":
        return "conference"
    if t == "article":
        return "journal"
    if t in ("phdthesis", "mastersthesis"):
        return "thesis"
    return "other"


def _authors(packed: str) -> list[str]:
    items = []
    for part in (packed or "").split("|"):
        if "~" in part:
            ordinal, name = part.split("~", 1)
            # DBLP disambiguates homonyms with a four-digit suffix ("Hao Zhang 0025").
            items.append((int(ordinal) if ordinal.isdigit() else 0, re.sub(r"\s+\d{4}$", "", name)))
    items.sort()
    return [name for _, name in items]


def to_record(b: dict) -> dict | None:
    def val(k):
        return (b.get(k) or {}).get("value")

    uri = val("p") or ""
    if not uri.startswith("https://dblp.org/rec/"):
        return None
    key = uri[len("https://dblp.org/rec/") :]
    venue = val("venue") or ""
    if key.startswith("journals/corr/"):
        venue = "arXiv"
    return records.make(
        "dblp",
        {"dblp": key, "doi": val("doi")},
        val("title"),
        authors=_authors(val("authors") or ""),
        year=val("year"),
        venue=venue or None,
        venue_type=_venue_type(val("type") or "", venue, key),
    )


def _run(query: str) -> list[dict]:
    data = net.get_json("dblp", ENDPOINT, params={"query": query}, headers={"Accept": "application/sparql-results+json"})
    if "exception" in data:
        raise net.SourceError("dblp: %s" % util.norm_space(str(data["exception"]))[:200])
    return [r for r in (to_record(b) for b in data.get("results", {}).get("bindings", [])) if r]


def search(query: str, limit: int = 10, year_from: int | None = None, year_to: int | None = None):
    recs = _run(build_search(query))
    if year_from:
        recs = [r for r in recs if r.get("year") and r["year"] >= year_from]
    if year_to:
        recs = [r for r in recs if r.get("year") and r["year"] <= year_to]
    total = len(recs)
    # No relevance score is available: show published work first, then the newest.
    recs.sort(key=lambda r: (r.get("venue_type") == "preprint", -(r.get("year") or 0)))
    return recs[:limit], ("%d+" % total if total >= INNER_LIMIT else total)


def get(kind: str, value: str) -> dict | None:
    if kind != "dblp":
        return None
    if not re.match(r"^[\w\-/.]+$", value):
        return None
    recs = _run(build_get(value))
    return recs[0] if recs else None
