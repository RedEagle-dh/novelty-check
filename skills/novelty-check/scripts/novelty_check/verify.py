"""Check a report: every link must be a scholarly record that exists, and its text must fit."""

from __future__ import annotations

import re
import urllib.parse

from . import ids, net, records, resolve, util
from .sources import doi as doi_source

MD_LINK = re.compile(r"\[([^\]]*)\]\((<?https?://[^)\s>]+>?)(?:\s+\"[^\"]*\")?\)")
BARE_URL = re.compile(r"(?<![(<\[])\bhttps?://[^\s)>\]]+")


def extract_links(markdown: str) -> list[tuple[str, str, int]]:
    """Return (text, url, line number) for markdown links and bare URLs."""
    out = []
    for lineno, line in enumerate(markdown.splitlines(), 1):
        covered = []
        for m in MD_LINK.finditer(line):
            out.append((m.group(1), m.group(2).strip("<>"), lineno))
            covered.append(m.span())
        for m in BARE_URL.finditer(line):
            if any(a <= m.start() < b for a, b in covered):
                continue
            out.append(("", m.group(0).rstrip(".,;"), lineno))
    return out


def host_of(url: str) -> str:
    host = urllib.parse.urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def similarity(a: str, b: str) -> float:
    wa = {w for w in util.norm_title(a).split() if w not in util.STOPWORDS}
    wb = {w for w in util.norm_title(b).split() if w not in util.STOPWORDS}
    if not wa or not wb:
        return 1.0
    return len(wa & wb) / len(wa)


def check(markdown: str, store: records.Store | None) -> dict:
    results = []
    cache: dict[str, dict] = {}
    for text, url, lineno in extract_links(markdown):
        item = {"line": lineno, "url": url, "text": text}
        host = host_of(url)
        if host not in ids.SCHOLARLY_HOSTS:
            item.update(status="error", message="not a scholarly record link (%s). Cite the paper's record URL instead." % host)
            results.append(item)
            continue
        pair = ids.parse_id(url)
        if not pair:
            item.update(status="error", message="link points to a scholarly site but not to a paper record")
            results.append(item)
            continue
        idstr = ids.id_str(*pair)
        item["id"] = idstr
        if idstr not in cache:
            cache[idstr] = _resolve(idstr, store)
        outcome = cache[idstr]
        item.update(outcome)
        if outcome["status"] == "ok" and text and len(util.norm_title(text).split()) >= 4:
            title = outcome.get("title") or ""
            if similarity(text, title) < 0.5 and util.norm_title(title) not in util.norm_title(text):
                item.update(status="warning", message="link text does not match the record's title: %s" % title)
        results.append(item)
    summary = {
        "links": len(results),
        "errors": sum(1 for r in results if r["status"] == "error"),
        "warnings": sum(1 for r in results if r["status"] == "warning"),
        "unchecked": sum(1 for r in results if r["status"] == "unchecked"),
    }
    return {"summary": summary, "results": results}


def _resolve(idstr: str, store: records.Store | None) -> dict:
    kind = idstr.split(":", 1)[0]
    try:
        if kind == "openreview":
            rec = store.lookup(idstr) if store else None
            if not rec:
                return {"status": "error", "message": "OpenReview record not in this run's search results"}
            return {"status": "ok", "title": rec.get("title"), "message": "found in this run's OpenReview search results"}
        rec = resolve.lookup(idstr, store=None, fresh=True)
        return {"status": "ok", "title": rec.get("title")}
    except resolve.NotFound as e:
        if kind == "doi":
            # The paper databases don't hold every DOI; doi.org itself is the final word.
            title = _doi_title(idstr.split(":", 1)[1])
            if title is not None:
                return {"status": "ok", "title": title, "message": "registered at doi.org"}
        return {"status": "error", "message": str(e)}
    except net.SourceError as e:
        return {"status": "unchecked", "message": "could not check right now: %s" % e}


def _doi_title(doi: str) -> str | None:
    try:
        entry = doi_source.bibtex(doi)
    except net.SourceError:
        return None
    if not entry:
        return None
    m = re.search(r"\btitle\s*=\s*[{\"](.+?)[}\"]\s*[,}]", entry, re.S)
    return util.norm_space(m.group(1).replace("{", "").replace("}", "")) if m else ""
