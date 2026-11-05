"""The common paper record, duplicate removal, the run's record store and text output."""

from __future__ import annotations

import json
import os
import re

from . import ids, util

VENUE_TYPES = ("conference", "journal", "workshop", "preprint", "submission", "report", "thesis", "other")
RATINGS = {"high": 3, "medium": 2, "low": 1}
UNPUBLISHED = ("preprint", "submission")


def make(
    source: str,
    ids_: dict,
    title: str | None,
    authors: list | None = None,
    year: int | None = None,
    venue: str | None = None,
    venue_type: str | None = None,
    abstract: str | None = None,
    citation_count: int | None = None,
    fulltext_url: str | None = None,
    **extra,
) -> dict:
    rec = {
        "id": None,
        "ids": {k: v for k, v in ids_.items() if v},
        "title": title,
        "authors": [util.norm_space(a) for a in (authors or []) if isinstance(a, str) and util.norm_space(a)],
        "year": _int(year),
        "venue": util.norm_space(venue) or None,
        "venue_type": venue_type if venue_type in VENUE_TYPES else ("other" if venue_type else None),
        "abstract": abstract,
        "citation_count": _int(citation_count),
        "url": None,
        "fulltext_url": fulltext_url or None,
        "found_in": [source],
    }
    rec.update({k: v for k, v in extra.items() if v is not None})
    return finalize(rec)


def _int(v):
    try:
        return int(v) if v is not None and v != "" else None
    except (TypeError, ValueError):
        return None


def finalize(rec: dict) -> dict:
    clean = {}
    for kind, value in (rec.get("ids") or {}).items():
        if not value:
            continue
        pair = ids.normalize_pair(kind, str(value))
        if pair and not clean.get(pair[0]):
            clean[pair[0]] = pair[1]
    rec["ids"] = clean
    title = util.norm_space(rec.get("title"))
    if title.endswith(".") and not title.endswith(".."):
        title = title[:-1]
    rec["title"] = title or None
    abstract = util.norm_space(rec.get("abstract"))
    rec["abstract"] = abstract or None
    rec["id"] = ids.canonical(clean)
    rec["url"] = ids.record_url(clean)
    return rec


def keys_of(rec: dict) -> list[str]:
    return [ids.id_str(k, v) for k, v in rec.get("ids", {}).items() if v]


def _years_close(a: dict, b: dict) -> bool:
    ya, yb = a.get("year"), b.get("year")
    return ya is None or yb is None or abs(ya - yb) <= 1


def _is_unpublished(rec: dict) -> bool:
    return not rec.get("venue") or rec.get("venue_type") in UNPUBLISHED or rec.get("venue_type") is None


def merge(a: dict, b: dict) -> dict:
    """Combine two records of the same work. Annotations (rating, claims, notes, angles) are kept."""
    out = dict(a)
    out["ids"] = dict(b.get("ids", {}))
    out["ids"].update({k: v for k, v in a.get("ids", {}).items() if v})
    out["title"] = a.get("title") or b.get("title")
    if len(b.get("authors") or []) > len(a.get("authors") or []):
        out["authors"] = b["authors"]
    # Prefer the published version's venue and year over a preprint or submission.
    if _is_unpublished(a) and not _is_unpublished(b):
        out["venue"], out["venue_type"], out["year"] = b.get("venue"), b.get("venue_type"), b.get("year") or a.get("year")
    else:
        out["venue"] = a.get("venue") or b.get("venue")
        out["venue_type"] = a.get("venue_type") or b.get("venue_type")
        out["year"] = a.get("year") or b.get("year")
    abstracts = [x for x in (a.get("abstract"), b.get("abstract")) if x]
    out["abstract"] = max(abstracts, key=len) if abstracts else None
    counts = [x for x in (a.get("citation_count"), b.get("citation_count")) if x is not None]
    out["citation_count"] = max(counts) if counts else None
    out["fulltext_url"] = a.get("fulltext_url") or b.get("fulltext_url")
    out["found_in"] = _union(a.get("found_in"), b.get("found_in"))
    for key in ("status", "bibtex", "journal_ref"):
        if not out.get(key) and b.get(key):
            out[key] = b[key]
    # Annotations from `mark`.
    ra, rb = a.get("rating"), b.get("rating")
    if ra or rb:
        out["rating"] = ra if RATINGS.get(ra, 0) >= RATINGS.get(rb, 0) else rb
    for key in ("claims", "angles"):
        if a.get(key) or b.get(key):
            out[key] = sorted(_union(a.get(key), b.get(key)), key=_claim_sort)
    if a.get("notes") or b.get("notes"):
        out["notes"] = _union(a.get("notes"), b.get("notes"))
    return finalize(out)


def _claim_sort(c: str):
    m = re.match(r"^C(\d+)$", c or "")
    return (0, int(m.group(1)), "") if m else (1, 0, c or "")


def _union(x, y) -> list:
    seen, out = set(), []
    for item in list(x or []) + list(y or []):
        marker = json.dumps(item, sort_keys=True)
        if marker not in seen:
            seen.add(marker)
            out.append(item)
    return out


def dedup(records: list[dict]) -> list[dict]:
    """Merge records that describe the same work (shared ID, or same title within a year)."""
    n = len(records)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    index: dict[str, int] = {}
    for i, rec in enumerate(records):
        keys = keys_of(rec)
        nt = util.norm_title(rec.get("title"))
        if len(nt) >= 20:  # short, generic titles are not safe to match on
            keys.append("t:" + nt)
        for key in keys:
            j = index.get(key)
            if j is None:
                index[key] = i
                continue
            if key.startswith("t:") and not _years_close(records[j], rec):
                continue
            ri, rj = find(i), find(j)
            if ri != rj:
                parent[max(ri, rj)] = min(ri, rj)

    groups: dict[int, dict] = {}
    order: list[int] = []
    for i, rec in enumerate(records):
        root = find(i)
        if root in groups:
            groups[root] = merge(groups[root], rec)
        else:
            groups[root] = finalize(dict(rec))
            order.append(root)
    return [groups[r] for r in order]


def read_jsonl(path: str) -> list[dict]:
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        util.eprint("skipping a broken line in %s" % path)
    except OSError:
        pass
    return out


def write_jsonl(path: str, records: list[dict]) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


class Store:
    """Every record any command has seen in this run, so later commands need no API call."""

    def __init__(self, path: str):
        self.path = path
        self._by_key: dict[str, dict] | None = None

    def add(self, recs: list[dict]) -> None:
        recs = [r for r in recs if r.get("id")]
        util.append_lines(self.path, [json.dumps(_strip_annotations(r), ensure_ascii=False) for r in recs])
        self._by_key = None

    def _load(self) -> dict[str, dict]:
        if self._by_key is None:
            self._by_key = {}
            for rec in dedup(read_jsonl(self.path)):
                for key in keys_of(rec):
                    self._by_key[key] = rec
        return self._by_key

    def lookup(self, idstr: str) -> dict | None:
        pair = ids.parse_id(idstr)
        if not pair:
            return None
        return self._load().get(ids.id_str(*pair))


def _strip_annotations(rec: dict) -> dict:
    return {k: v for k, v in rec.items() if k not in ("rating", "claims", "notes", "angles")}


def venue_label(rec: dict) -> str:
    venue = rec.get("venue") or "unknown venue"
    vt = rec.get("venue_type")
    label = "%s (%s)" % (venue, vt) if vt and vt.lower() not in venue.lower() else venue
    if rec.get("status"):
        label += " [%s]" % rec["status"]
    return label


def authors_label(rec: dict, n: int = 4) -> str:
    authors = rec.get("authors") or []
    if not authors:
        return "authors unknown"
    names = [re.sub(r"\s+\d{4}$", "", a) for a in authors[:n]]  # DBLP disambiguation numbers
    return ", ".join(names) + (" et al." if len(authors) > n else "")


def brief(rec: dict, number: int | None = None, abstract_chars: int = 400) -> str:
    head = "[%d] " % number if number is not None else ""
    meta = [str(rec.get("year") or "n.d."), venue_label(rec)]
    if rec.get("citation_count") is not None:
        meta.append("cited %d" % rec["citation_count"])
    meta.append("via " + ",".join(rec.get("found_in") or []))
    lines = ["%s%s  ·  %s" % (head, rec.get("id"), "  ·  ".join(meta)), "    " + (rec.get("title") or "(no title)")]
    lines.append("    " + authors_label(rec))
    if rec.get("rating") or rec.get("claims"):
        ann = "    rating: %s" % (rec.get("rating") or "-")
        if rec.get("claims"):
            ann += "  ·  claims: %s" % ",".join(rec["claims"])
        if rec.get("angles"):
            ann += "  ·  angles: %s" % ",".join(rec["angles"])
        lines.append(ann)
    for note in rec.get("notes") or []:
        text = note.get("text") if isinstance(note, dict) else str(note)
        who = note.get("angle") if isinstance(note, dict) else None
        lines.append("    note%s: %s" % (" (%s)" % who if who else "", text))
    if abstract_chars:
        abstract = rec.get("abstract")
        if not abstract:
            lines.append("    abstract: (none yet; run `get %s`)" % rec.get("id"))
        else:
            if abstract_chars > 0 and len(abstract) > abstract_chars:
                abstract = abstract[:abstract_chars].rsplit(" ", 1)[0] + " …"
            lines.append("    abstract: " + abstract)
    return "\n".join(lines)


def sort_key(rec: dict):
    return (
        -RATINGS.get(rec.get("rating"), 0),
        -len(rec.get("claims") or []),
        -(rec.get("citation_count") or 0),
    )
