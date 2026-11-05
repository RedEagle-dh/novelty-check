"""Look up one work by ID across sources, filling in what each source lacks."""

from __future__ import annotations

from . import ids, net, records
from .sources import Skipped, arxiv, dblp, openalex, s2

# Which sources can look up which kind of ID, in the order they are asked.
LOOKUP_ORDER = {
    "doi": (s2, openalex),
    "arxiv": (arxiv, s2, openalex),
    "s2": (s2,),
    "dblp": (dblp, s2),
    "openalex": (openalex,),
    "openreview": (),
}


class NotFound(Exception):
    pass


def lookup(idstr: str, store: records.Store | None = None, fresh: bool = False, errors: list | None = None) -> dict:
    """Return a merged record. Raises NotFound when no source knows the ID.

    Uses the run's store first. A fresh lookup asks the sources even if the store has a record.
    Source failures are appended to `errors` (if given) instead of being raised, unless every
    source failed, in which case the first failure is raised.
    """
    pair = ids.parse_id(idstr)
    if not pair:
        raise NotFound("not a recognised paper ID: %s" % idstr)
    kind, value = pair
    known = store.lookup(ids.id_str(kind, value)) if store else None
    if known and not fresh and known.get("abstract"):
        return known

    found: list[dict] = [known] if known else []
    failures: list[net.SourceError] = []
    queue = [(kind, value)]
    asked: set = set()
    while queue:
        k, v = queue.pop(0)
        for source in LOOKUP_ORDER.get(k, ()):
            if (source.__name__, k) in asked:
                continue
            asked.add((source.__name__, k))
            try:
                rec = source.get(k, v)
            except Skipped:
                continue
            except net.SourceError as e:
                failures.append(e)
                continue
            if rec:
                found.append(rec)
                merged = records.dedup(found)[0]
                # An arXiv preprint may have a published version; one more lookup finds it.
                still_preprint = k == "arxiv" and merged.get("venue_type") == "preprint" and source is arxiv
                if merged.get("abstract") and merged.get("authors") and not still_preprint:
                    queue = []
                    break
                # e.g. a DBLP hit with a DOI: ask by DOI next to get an abstract.
                for next_kind in ("doi", "arxiv"):
                    nv = merged["ids"].get(next_kind)
                    if nv and (next_kind, nv) != (k, v):
                        queue.append((next_kind, nv))
    if errors is not None:
        errors.extend(str(e) for e in failures)
    if not found:
        # "Not found" only when every source answered; a failed source might have known it.
        if failures:
            raise failures[0]
        if kind == "openreview":
            raise NotFound("openreview:%s is not in this run's search results (OpenReview can't be looked up by ID)" % value)
        raise NotFound("no source knows %s" % ids.id_str(kind, value))
    merged = records.dedup(found)
    rec = merged[0]
    if store:
        store.add([rec])
    return rec
