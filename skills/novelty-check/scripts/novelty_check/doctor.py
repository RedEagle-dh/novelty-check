"""`doctor`: is everything in place for a full run? Prints what is missing and how to fix it."""

from __future__ import annotations

import os
import shutil
import sys

from . import keys, net, util
from .sources import arxiv, dblp, openalex, openreview, s2

S2_FORM = "https://www.semanticscholar.org/product/api#api-key-form"
OPENALEX_SETTINGS = "https://openalex.org/settings/api"
PROBE_DOI = "10.1145/3600006.3613165"


def _probe(source: str, url: str, params=None, headers=None) -> tuple[str, str]:
    """Return (state, detail) where state is ok, limited, rejected, failed or offline."""
    # Semantic Scholar answers 429 at busy times even to a valid key, so one 429 proves nothing.
    retries = 3 if source.startswith("s2") else 0
    try:
        resp = net.fetch(source, url, params=params, headers=headers, cache=False, retries=retries, timeout=20)
    except net.SourceError as e:
        return ("offline" if e.kind == "network" else "failed", str(e))
    if resp.status == 200:
        return ("ok", "")
    if resp.status in (401, 403):
        return ("rejected", "HTTP %d: %s" % (resp.status, util.norm_space(resp.text)[:120]))
    if resp.status == 429:
        return ("limited", "HTTP 429 (too many requests) on every try")
    return ("failed", "HTTP %d" % resp.status)


def run() -> dict:
    report: dict = {}
    report["python"] = {"version": sys.version.split()[0], "ok": sys.version_info >= (3, 9)}
    report["cache_dir"] = util.cache_dir()
    report["cache_dir_is_fallback"] = report["cache_dir"] == os.path.join(os.getcwd(), ".novelty-check-cache")
    report["keys_file"] = {
        "path": keys.keys_path(),
        "exists": os.path.exists(keys.keys_path()),
        "warning": keys.file_mode_problem(),
    }
    report["keys"] = {name: {"present": bool(keys.get(name)), "origin": keys.origin(name)} for name in ("s2", "openalex")}
    report["pdftotext"] = shutil.which("pdftotext")

    s2_headers = {"x-api-key": keys.get("s2")} if keys.get("s2") else None
    oa_params = {"select": "id"}
    if keys.get("openalex"):
        oa_params["api_key"] = keys.get("openalex")
    probes = {
        "s2": _probe(
            "s2" if s2_headers else "s2-keyless", "%s/paper/DOI:%s" % (s2.GRAPH, PROBE_DOI), {"fields": "title"}, s2_headers
        ),
        "openalex": _probe("openalex", openalex.BASE + "/works/W4387321091", oa_params),
        "arxiv": _probe("arxiv", arxiv.API, {"id_list": "2309.06180", "max_results": 1}),
        "dblp": _probe("dblp", dblp.ENDPOINT, {"query": "ASK { ?s ?p ?o }"}, {"Accept": "application/sparql-results+json"}),
        "openreview": _probe(
            "openreview", openreview.API + "/notes/search", {"term": "attention", "type": "terms", "source": "forum", "limit": 1}
        ),
        "doi.org": _probe("doi", "https://doi.org/" + PROBE_DOI, None, {"Accept": "application/x-bibtex"}),
    }
    report["sources"] = {k: {"state": v[0], "detail": v[1]} for k, v in probes.items()}
    report["mode"], report["mode_reason"] = decide_mode(report)
    return report


def decide_mode(r: dict) -> tuple[str, str]:
    """FULL, REDUCED or BLOCKED, with a sentence saying why."""
    sources = r["sources"]
    if all(s["state"] == "offline" for s in sources.values()):
        return "blocked", "No source could be reached; this agent seems to have no network access."
    unreachable = [n for n, s in sources.items() if n != "s2" and s["state"] in ("offline", "failed")]
    tail = " Not reachable right now: %s." % ", ".join(unreachable) if unreachable else ""
    s2_state = sources["s2"]["state"]
    if not r["keys"]["s2"]["present"]:
        return "reduced", "No Semantic Scholar key, so its keyword search is off; the other sources work." + tail
    if s2_state == "rejected":
        return "reduced", "Semantic Scholar rejected the key, so its searches will fail; the other sources work." + tail
    if s2_state in ("offline", "failed"):
        return "reduced", "Semantic Scholar can't be reached right now; the other sources work." + tail
    if s2_state == "limited":
        return "full", (
            "Semantic Scholar accepted the key but answered 'too many requests' to every try of this check. "
            "It does that at busy times; searches retry automatically, and calls that still fail are listed "
            "in the run's search log." + tail
        )
    return "full", ("All sources are available." if not tail else "Semantic Scholar works." + tail)


def render(r: dict) -> str:
    out = ["novelty-check doctor", ""]

    def line(label: str, value: str) -> None:
        out.append("  %-22s %s" % (label, value))

    py = r["python"]
    line("Python", "%s %s" % (py["version"], "ok" if py["ok"] else "TOO OLD: needs 3.9 or later"))
    line("Cache", r["cache_dir"] + (" (fallback inside the working directory)" if r["cache_dir_is_fallback"] else ""))
    kf = r["keys_file"]
    line("Keys file", "%s%s" % (kf["path"], "" if kf["exists"] else " (not created yet)"))
    if kf["warning"]:
        line("", "WARNING: " + kf["warning"])
    for name, label in (("s2", "Semantic Scholar key"), ("openalex", "OpenAlex key")):
        k = r["keys"][name]
        line(label, "set (%s)" % k["origin"] if k["present"] else "MISSING")
    line("pdftotext", r["pdftotext"] or "not found (optional: PDF full text)")
    out.append("")
    out.append("  Sources:")
    for name, s in r["sources"].items():
        line("  " + name, s["state"] + (" — " + s["detail"] if s["detail"] and s["state"] != "ok" else ""))
    out.append("")
    out.append("Mode: %s. %s" % (r["mode"].upper(), r["mode_reason"]))
    hints = hints_for(r)
    if hints:
        out.append("")
        out.append("To fix:")
        out.extend("  - " + h for h in hints)
    return "\n".join(out)


def hints_for(r: dict) -> list[str]:
    hints = []
    me = "sh <skill dir>/scripts/papers"
    if not r["keys"]["s2"]["present"]:
        hints.append(
            "Semantic Scholar key: request one at %s (free, approval can take a few days). "
            "Then run `%s setup` in your own terminal, or set S2_API_KEY." % (S2_FORM, me)
        )
    elif r["sources"]["s2"]["state"] == "rejected":
        hints.append("Semantic Scholar rejected the key. Check it, then run `%s setup` again." % me)
    if not r["keys"]["openalex"]["present"]:
        hints.append(
            "OpenAlex key: without one, everyone on your network shares about 100 searches a day. "
            "Get a free key at %s, or run `%s setup --request-openalex-key you@example.org` "
            "(OpenAlex emails you a link), then `%s setup`." % (OPENALEX_SETTINGS, me, me)
        )
    elif r["sources"]["openalex"]["state"] == "rejected":
        hints.append("OpenAlex rejected the key. Check it, then run `%s setup` again." % me)
    if r["mode"] == "blocked":
        hints.append(
            "Allow network access for this agent. Codex: add `[sandbox_workspace_write]` with "
            "`network_access = true` to ~/.codex/config.toml (or approve network use when asked). "
            "Other agents: allow outbound HTTPS to the paper APIs."
        )
    if r["keys_file"]["warning"]:
        hints.append(r["keys_file"]["warning"])
    if not r["python"]["ok"]:
        hints.append("Install Python 3.9 or later.")
    return hints
