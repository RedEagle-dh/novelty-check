"""Command-line interface: `papers <command> …`. Run `papers --help` for the list."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import sys

from . import __version__, bib, doctor, fulltext, ids, keys, net, records, resolve, util, verify
from .sources import ALL_SOURCES, DEFAULT_SOURCES, LABELS, Skipped, arxiv, dblp, openalex, openreview, s2

MODULES = {"s2": s2, "openalex": openalex, "arxiv": arxiv, "dblp": dblp, "openreview": openreview}


# --- helpers -------------------------------------------------------------------------------


def _store(args) -> records.Store:
    base = args.run or util.cache_dir()
    return records.Store(os.path.join(base, "records.jsonl"))


def _log(args, entry: dict) -> None:
    if not args.run:
        return
    entry = dict(entry)
    entry.setdefault("time", util.now_iso())
    if args.angle:
        entry.setdefault("angle", args.angle)
    util.append_lines(os.path.join(args.run, "search-log.jsonl"), [json.dumps(entry, ensure_ascii=False)])


def _parse_sources(spec: str) -> list[str]:
    out: list[str] = []
    for part in spec.split(","):
        part = part.strip().lower()
        if not part:
            continue
        if part == "default":
            names = list(DEFAULT_SOURCES)
        elif part == "all":
            names = list(ALL_SOURCES)
        elif part in MODULES:
            names = [part]
        else:
            raise SystemExit("unknown source '%s' (choose from: default, all, %s)" % (part, ", ".join(MODULES)))
        out.extend(n for n in names if n not in out)
    return out


def _interleave(lists: list[list[dict]]) -> list[dict]:
    out = []
    for i in range(max((len(x) for x in lists), default=0)):
        for lst in lists:
            if i < len(lst):
                out.append(lst[i])
    return out


def _print_records(recs: list[dict], fmt: str, abstract_chars: int, start: int = 1) -> None:
    if fmt == "jsonl":
        for r in recs:
            print(json.dumps(r, ensure_ascii=False))
        return
    for n, r in enumerate(recs, start):
        print(records.brief(r, n, abstract_chars))
        print()


def _require_run(args) -> None:
    if not args.run:
        raise SystemExit("this command needs --run <run folder> (from `init-run`)")


# --- commands ------------------------------------------------------------------------------


def cmd_init_run(args) -> int:
    base = os.path.abspath(args.base or os.getcwd())
    root = os.path.join(base, "novelty-checks")
    name = "%s-%s" % (util.today(), util.slugify(args.title))
    path = os.path.join(root, name)
    n = 2
    while os.path.exists(path):
        path = os.path.join(root, "%s-%d" % (name, n))
        n += 1
    for sub in ("notes", "candidates", "assessments", "fulltext"):
        os.makedirs(os.path.join(path, sub))
    with open(os.path.join(path, "run.json"), "w", encoding="utf-8") as f:
        json.dump({"title": args.title, "created": util.now_iso(), "novelty_check_version": __version__}, f, indent=2)
    print(path)
    return 0


def cmd_doctor(args) -> int:
    report = doctor.run()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(doctor.render(report))
    return 0 if report["mode"] != "blocked" else 1


def cmd_setup(args) -> int:
    if args.request_openalex_key:
        result = openalex.request_key(args.request_openalex_key)
        payload = result["response"]
        key = None
        if isinstance(payload, dict):
            key = payload.get("api_key") or payload.get("key")
        if key and isinstance(key, str):
            path = keys.save("openalex", key)
            print("OpenAlex sent a key; it is saved in %s. It works once you click the link in the email." % path)
        elif result["status"] in (200, 201, 202):
            print(
                "OpenAlex will email a key to %s. Click the link in the email, then run `setup` and paste the key."
                % args.request_openalex_key
            )
        else:
            print("OpenAlex answered HTTP %d: %s" % (result["status"], json.dumps(payload)[:300]))
            return 1
        return 0
    if args.set:
        value = sys.stdin.readline().strip()
        if not value:
            raise SystemExit("no key on standard input")
        print("Saved the %s key in %s" % (keys.LABELS[args.set], keys.save(args.set, value)))
        return 0
    if args.show:
        for name, label in keys.LABELS.items():
            print("%-17s %s" % (label + ":", "set (%s)" % keys.origin(name) if keys.get(name) else "missing"))
        return 0
    if not sys.stdin.isatty():
        print(
            "Run `setup` in your own terminal to type keys without echo, or pipe one key in:\n"
            "  printf '%s' \"$KEY\" | sh <skill dir>/scripts/papers setup --set s2\n"
            "Or set S2_API_KEY / OPENALEX_API_KEY in your environment."
        )
        return 2
    print("Paste each key and press Enter (input is hidden). Leave empty to keep the current value.")
    for name, label in keys.LABELS.items():
        current = "set" if keys.get(name) else "missing"
        value = getpass.getpass("%s API key [%s]: " % (label, current)).strip()
        if value:
            print("  saved in %s" % keys.save(name, value))
    return 0


def cmd_search(args) -> int:
    sources = _parse_sources(args.source)
    per_source: list[list[dict]] = []
    summary = []
    failures = 0
    for src in sources:
        entry = {"cmd": "search", "source": src, "query": args.query, "year_from": args.year_from, "year_to": args.year_to}
        try:
            if src == "openalex":
                recs, total = openalex.search(args.query, args.limit, args.year_from, args.year_to, any_field=args.any_field)
            else:
                recs, total = MODULES[src].search(args.query, args.limit, args.year_from, args.year_to)
            entry.update(status="ok", hits=len(recs), total=total)
            per_source.append(recs)
            summary.append("%s %d of %s" % (LABELS[src], len(recs), total if total is not None else "?"))
        except Skipped as e:
            entry.update(status="skipped", hits=0, error=str(e))
            summary.append("%s skipped (%s)" % (LABELS[src], e))
        except net.SourceError as e:
            failures += 1
            entry.update(status="error", hits=0, error=str(e))
            summary.append("%s FAILED (%s)" % (LABELS[src], e))
        _log(args, entry)
    merged = records.dedup(_interleave(per_source))
    _store(args).add(merged)
    if args.format == "brief":
        print("Searched: " + " · ".join(summary))
        print("%d distinct works.\n" % len(merged))
    else:
        for line in summary:
            util.eprint(line)
    _print_records(merged, args.format, args.abstract_chars)
    return 1 if failures and failures == len(sources) else 0


def cmd_get(args) -> int:
    store = _store(args)
    status = 0
    out = []
    for raw in args.ids:
        errors: list[str] = []
        try:
            rec = resolve.lookup(raw, store=store, fresh=args.fresh, errors=errors)
            out.append(rec)
        except (resolve.NotFound, net.SourceError) as e:
            util.eprint("%s: %s" % (raw, e))
            status = 1
        for err in errors:
            util.eprint("note: %s" % err)
    _print_records(out, args.format, args.abstract_chars)
    return status


def _seed_lookup_ids(rec: dict) -> list[tuple[str, str]]:
    order = ("s2", "doi", "arxiv", "dblp", "openalex")
    return [(k, rec["ids"][k]) for k in order if rec["ids"].get(k)]


def cmd_expand(args) -> int:
    store = _store(args)
    try:
        seed = resolve.lookup(args.id, store=store)
    except (resolve.NotFound, net.SourceError) as e:
        util.eprint("%s: %s" % (args.id, e))
        return 1
    modes = ["citations", "references", "recommend"] if args.mode == "all" else [args.mode]
    found: list[dict] = []
    summary = []
    for mode in modes:
        entry = {"cmd": "expand", "seed": seed["id"], "seed_title": seed.get("title"), "mode": mode, "query": args.query}
        recs = None
        errors = []
        attempts = []
        if not (mode == "citations" and args.query):
            attempts.append("s2")
        if mode != "recommend":
            attempts.append("openalex")
        for src in attempts:
            for kind, value in _seed_lookup_ids(seed):
                try:
                    if src == "s2":
                        if kind not in ("s2", "doi", "arxiv", "dblp"):
                            continue
                        recs = s2.expand(kind, value, mode, args.limit)
                    else:
                        if kind not in ("openalex", "doi", "arxiv"):
                            continue
                        recs = openalex.expand(kind, value, mode, args.limit, query=args.query if mode == "citations" else None)
                    entry["source"] = src
                    break
                except net.SourceError as e:
                    errors.append(str(e))
            if recs is not None:
                break
        if recs is None:
            entry.update(status="error", hits=0, error="; ".join(errors) or "no usable ID for this seed")
            summary.append("%s FAILED" % mode)
        else:
            recs = [r for r in recs if r.get("id") != seed.get("id")]
            entry.update(status="ok", hits=len(recs))
            summary.append("%s %d (%s)" % (mode, len(recs), LABELS[entry["source"]]))
            found.extend(recs)
        _log(args, entry)
    merged = [r for r in records.dedup(found) if not set(records.keys_of(r)) & set(records.keys_of(seed))]
    store.add(merged)
    if args.format == "brief":
        print("Seed: %s  %s" % (seed["id"], seed.get("title")))
        print("Expanded: " + " · ".join(summary))
        print("%d distinct works.\n" % len(merged))
    _print_records(merged, args.format, args.abstract_chars)
    return 1 if all("FAILED" in s for s in summary) else 0


def cmd_fulltext(args) -> int:
    store = _store(args)
    try:
        rec = resolve.lookup(args.id, store=store)
        if not rec["ids"].get("arxiv") and not rec.get("fulltext_url"):
            rec = resolve.lookup(args.id, store=store, fresh=True)
    except (resolve.NotFound, net.SourceError) as e:
        util.eprint("%s: %s" % (args.id, e))
        return 1
    out_dir = os.path.join(args.run, "fulltext") if args.run else os.path.join(util.cache_dir(), "fulltext")
    result = fulltext.fetch(rec, out_dir)
    if args.json:
        print(json.dumps(result, indent=2))
        return 0 if "error" not in result else 1
    print("%s  %s" % (rec["id"], rec.get("title")))
    if "error" in result:
        print("No full text: %s" % result["error"])
        for url in result.get("tried", []):
            print("  tried: %s" % url)
        return 1
    print("Saved: %s" % result["path"])
    print("From: %s (%s)" % (result["source_url"], result["kind"]))
    if result.get("chars"):
        print("Length: %d characters" % result["chars"])
    if result.get("hint"):
        print(result["hint"])
    if result.get("headings"):
        print("Sections:")
        for h in result["headings"]:
            print("  " + h)
    return 0


CLAIM = re.compile(r"^(C\d+|problem|method|setting)$")


def cmd_mark(args) -> int:
    store = _store(args)
    try:
        rec = resolve.lookup(args.id, store=store)
    except (resolve.NotFound, net.SourceError) as e:
        util.eprint("%s: %s" % (args.id, e))
        return 1
    claims = [c.strip() for c in (args.claims or "").split(",") if c.strip()]
    bad = [c for c in claims if not CLAIM.match(c)]
    if bad:
        raise SystemExit("claims must look like C1,C2 (or problem, method, setting); got: %s" % ", ".join(bad))
    rec = dict(rec)
    rec["rating"] = args.rating
    rec["claims"] = claims
    rec["angles"] = [args.angle] if args.angle else []
    rec["notes"] = [{"angle": args.angle, "text": args.note}] if args.note else []
    util.append_lines(args.to, [json.dumps(rec, ensure_ascii=False)])
    print("marked %s as %s%s -> %s" % (rec["id"], args.rating, " (%s)" % ",".join(claims) if claims else "", args.to))
    return 0


def _filtered(recs: list[dict], args) -> list[dict]:
    if args.min_rating:
        floor = records.RATINGS[args.min_rating]
        recs = [r for r in recs if records.RATINGS.get(r.get("rating"), 0) >= floor]
    recs = sorted(recs, key=records.sort_key)
    return recs[: args.top] if args.top else recs


def cmd_merge(args) -> int:
    recs = []
    for path in args.files:
        recs.extend(records.read_jsonl(path))
    merged = sorted(records.dedup(recs), key=records.sort_key)
    records.write_jsonl(args.out, merged)
    counts = {k: sum(1 for r in merged if r.get("rating") == k) for k in ("high", "medium", "low")}
    print(
        "Merged %d entries from %d files into %d works (%s) -> %s\n"
        % (len(recs), len(args.files), len(merged), ", ".join("%d %s" % (v, k) for k, v in counts.items()), args.out)
    )
    _print_records(_filtered(merged, args), "brief", args.abstract_chars)
    return 0


def cmd_show(args) -> int:
    recs = records.read_jsonl(args.file)
    _print_records(_filtered(recs, args), args.format, args.abstract_chars)
    return 0


def cmd_bibtex(args) -> int:
    store = _store(args)
    wanted: list[str] = list(args.ids or [])
    if args.from_report:
        with open(args.from_report, encoding="utf-8") as f:
            text = f.read()
        for _, url, _ in verify.extract_links(text):
            if verify.host_of(url) in ids.SCHOLARLY_HOSTS and ids.parse_id(url):
                wanted.append(url)
    recs: list[dict] = []
    seen: set = set()
    status = 0
    for raw in wanted:
        try:
            rec = resolve.lookup(raw, store=store)
        except (resolve.NotFound, net.SourceError) as e:
            util.eprint("skipped %s: %s" % (raw, e))
            status = 1
            continue
        if set(records.keys_of(rec)) & seen:
            continue
        seen.update(records.keys_of(rec))
        recs.append(rec)
    entries = ["% BibTeX generated by novelty-check " + __version__ + " on " + util.today()]
    for rec, key in zip(recs, bib.unique_keys(recs)):
        entry, origin = bib.entry_for(rec, key)
        entries.append("%% %s (%s)\n%s" % (rec["id"], origin, entry))
        util.eprint("%-28s %-40s %s" % (key, rec["id"], origin))
    text = "\n\n".join(entries) + "\n"
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print("Wrote %d entries to %s" % (len(recs), args.out))
    else:
        print(text)
    return status


def cmd_verify(args) -> int:
    with open(args.report, encoding="utf-8") as f:
        text = f.read()
    result = verify.check(text, _store(args))
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        s = result["summary"]
        for r in result["results"]:
            if r["status"] == "ok":
                continue
            print("line %d: %s: %s\n    %s" % (r["line"], r["status"].upper(), r.get("message", ""), r["url"]))
        print(
            "%d links checked: %d errors, %d warnings, %d could not be checked."
            % (s["links"], s["errors"], s["warnings"], s["unchecked"])
        )
        if s["errors"]:
            print("Fix or remove every ERROR, then run verify again.")
        elif s["unchecked"]:
            print("Some links could not be checked (network or rate limit). Run verify again in a minute.")
        else:
            print("All links resolve to scholarly records.")
    return 1 if result["summary"]["errors"] else 0


def _cell(entries: list[dict], notes: list[str]) -> str:
    """One table cell for the calls of one query to one source: hits, or why there are none."""
    if not entries:
        return "–"
    e = entries[-1]
    if e.get("status") == "ok":
        return str(e.get("hits", 0))
    msg = util.norm_space(e.get("error"))[:120]
    if msg not in notes:
        notes.append(msg)
    return "%s [%d]" % ("skipped" if e.get("status") == "skipped" else "failed", notes.index(msg) + 1)


def cmd_log_summary(args) -> int:
    _require_run(args)
    entries = records.read_jsonl(os.path.join(args.run, "search-log.jsonl"))
    searches = [e for e in entries if e.get("cmd") == "search"]
    expands = [e for e in entries if e.get("cmd") == "expand"]
    notes: list[str] = []
    queries = {(e.get("angle"), e.get("query")) for e in searches}
    print(
        "%d keyword queries (%d source calls, %d failed, %d skipped) and %d citation lookups."
        % (
            len(queries),
            len(searches),
            sum(1 for e in searches if e.get("status") == "error"),
            sum(1 for e in searches if e.get("status") == "skipped"),
            len(expands),
        )
    )
    times = [e["time"] for e in entries if e.get("time")]
    if times:
        print("Searched between %s and %s (UTC). Cells give the number of results shown per source.\n" % (min(times), max(times)))
    angles: dict = {}
    for e in searches:
        angles.setdefault(e.get("angle") or "(no angle)", {}).setdefault(e.get("query", ""), []).append(e)
    for angle, by_query in angles.items():
        used = [src for src in ALL_SOURCES if any(e.get("source") == src for rows in by_query.values() for e in rows)]
        print("#### %s\n" % angle)
        print("| Query | %s |" % " | ".join(LABELS[s] for s in used))
        print("|---|%s" % ("---|" * len(used)))
        for query, rows in by_query.items():
            cells = [_cell([e for e in rows if e.get("source") == src], notes) for src in used]
            print("| %s | %s |" % (query.replace("|", "\\|"), " | ".join(cells)))
        print()
    if expands:
        print("#### Citation following\n")
        print("| Seed | Citing works | Cited works | Recommended | Citing works matching keywords |")
        print("|---|---|---|---|---|")
        seeds: dict = {}
        for e in expands:
            seeds.setdefault((e.get("seed"), e.get("seed_title")), []).append(e)
        for (seed, title), rows in seeds.items():
            plain = [e for e in rows if not e.get("query")]
            matching = [e for e in rows if e.get("query")]
            cells = [_cell([e for e in plain if e.get("mode") == m], notes) for m in ("citations", "references", "recommend")]
            cells.append(", ".join("'%s': %s" % (e["query"], _cell([e], notes)) for e in matching) if matching else "–")
            label = "%s (%s)" % (seed, util.norm_space(title)[:70])
            print("| %s | %s |" % (label.replace("|", "\\|"), " | ".join(cells)))
        print()
    if notes:
        print("Notes:\n")
        for i, note in enumerate(notes, 1):
            print("%d. %s" % (i, note))
        print()
    return 0


# --- argument parsing --------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--run",
        default=os.environ.get("NOVELTY_CHECK_RUN"),
        help="run folder from init-run (enables the search log and record store)",
    )
    common.add_argument("--angle", help="search angle name, recorded in the log and on marked candidates")
    common.add_argument("--no-cache", action="store_true", help="ignore the 7-day response cache")

    out = argparse.ArgumentParser(add_help=False)
    out.add_argument("--format", choices=("brief", "jsonl"), default="brief")

    p = argparse.ArgumentParser(
        prog="papers", description="Search scholarly databases for prior work (novelty-check %s)." % __version__
    )
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init-run", parents=[common], help="create a run folder and print its path")
    s.add_argument("--title", required=True)
    s.add_argument("--base", help="directory to create novelty-checks/ in (default: current directory)")
    s.set_defaults(func=cmd_init_run)

    s = sub.add_parser("doctor", parents=[common], help="check Python, keys and source access")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_doctor)

    s = sub.add_parser("setup", parents=[common], help="store API keys (run it in your own terminal)")
    s.add_argument("--set", choices=sorted(keys.LABELS), help="read one key from standard input")
    s.add_argument("--show", action="store_true", help="show which keys are set (never the values)")
    s.add_argument("--request-openalex-key", metavar="EMAIL", help="ask OpenAlex to email a free key")
    s.set_defaults(func=cmd_setup)

    s = sub.add_parser("search", parents=[common, out], help="keyword search across sources")
    s.add_argument("--query", "-q", required=True)
    s.add_argument("--source", default="default", help="comma list: default (s2,openalex,arxiv,dblp), all, or source names")
    s.add_argument("--limit", type=int, default=10, help="results per source (default 10)")
    s.add_argument("--year-from", type=int)
    s.add_argument("--year-to", type=int)
    s.add_argument("--any-field", action="store_true", help="OpenAlex: don't restrict to the physical sciences domain")
    s.add_argument("--abstract-chars", type=int, default=400, help="abstract length shown (0 none, -1 full)")
    s.set_defaults(func=cmd_search)

    s = sub.add_parser("get", parents=[common, out], help="full record(s) with abstract")
    s.add_argument("ids", nargs="+")
    s.add_argument("--fresh", action="store_true", help="ask the sources even if the run already has the record")
    s.add_argument("--abstract-chars", type=int, default=-1)
    s.set_defaults(func=cmd_get)

    s = sub.add_parser("expand", parents=[common, out], help="follow citations from a seed paper")
    s.add_argument("id")
    s.add_argument("--mode", choices=("citations", "references", "recommend", "all"), default="all")
    s.add_argument("--limit", type=int, default=25, help="results per mode (default 25)")
    s.add_argument("--query", help="citations only: keep citing works that match these keywords (OpenAlex)")
    s.add_argument("--abstract-chars", type=int, default=300)
    s.set_defaults(func=cmd_expand)

    s = sub.add_parser("fulltext", parents=[common], help="save readable full text (arXiv HTML or open-access PDF)")
    s.add_argument("id")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_fulltext)

    s = sub.add_parser("mark", parents=[common], help="record a screened candidate with rating and claims")
    s.add_argument("id")
    s.add_argument("--to", required=True, help="candidates file, e.g. <run>/candidates/<angle>.jsonl")
    s.add_argument("--rating", required=True, choices=("high", "medium", "low"))
    s.add_argument("--claims", help="comma list of claims it touches, e.g. C1,C3")
    s.add_argument("--note", help="one sentence: why it matters or how it differs")
    s.set_defaults(func=cmd_mark)

    s = sub.add_parser("merge", parents=[common], help="merge candidate files, remove duplicates")
    s.add_argument("files", nargs="+")
    s.add_argument("--out", required=True)
    s.add_argument("--top", type=int, default=40)
    s.add_argument("--min-rating", choices=("high", "medium", "low"))
    s.add_argument("--abstract-chars", type=int, default=0)
    s.set_defaults(func=cmd_merge)

    s = sub.add_parser("show", parents=[common, out], help="list records from a JSONL file")
    s.add_argument("file")
    s.add_argument("--top", type=int)
    s.add_argument("--min-rating", choices=("high", "medium", "low"))
    s.add_argument("--abstract-chars", type=int, default=0)
    s.set_defaults(func=cmd_show)

    s = sub.add_parser("bibtex", parents=[common], help="BibTeX for IDs or for every work linked in a report")
    s.add_argument("ids", nargs="*")
    s.add_argument("--from-report")
    s.add_argument("--out")
    s.set_defaults(func=cmd_bibtex)

    s = sub.add_parser("verify", parents=[common], help="check that every link in a report is a real scholarly record")
    s.add_argument("report")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_verify)

    s = sub.add_parser("log-summary", parents=[common], help="the run's search log as Markdown tables")
    s.set_defaults(func=cmd_log_summary)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if getattr(args, "no_cache", False):
        net.disable_cache()
    if getattr(args, "run", None):
        args.run = os.path.abspath(args.run)
        if args.cmd != "init-run" and not os.path.isdir(args.run):
            raise SystemExit("run folder does not exist: %s (create it with init-run)" % args.run)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130
    except BrokenPipeError:
        return 0
