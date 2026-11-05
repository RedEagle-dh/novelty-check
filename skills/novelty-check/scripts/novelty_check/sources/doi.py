"""doi.org content negotiation: BibTeX for a DOI (Crossref, DataCite, …)."""

from __future__ import annotations

import urllib.parse

from .. import net


def bibtex(doi: str) -> str | None:
    url = "https://doi.org/" + urllib.parse.quote(doi, safe="/:;()._-")
    resp = net.fetch("doi", url, headers={"Accept": "application/x-bibtex; charset=utf-8"})
    if resp.status != 200:
        return None
    text = resp.text.strip()
    return text if text.startswith("@") else None
