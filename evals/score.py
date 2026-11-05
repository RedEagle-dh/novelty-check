"""Score a finished run against evals/expected.json.

    python3 evals/score.py <eval name> <run folder>

Passes when an expected paper is among the first five works under "Closest existing works" and
the verdict is one of the accepted ones. Works linked by preprint or by published version both
count, because the run's record store knows both IDs.
"""

from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "skills", "novelty-check", "scripts"))

from novelty_check import ids, records, verify  # noqa: E402

VERDICTS = ("Already done", "Largely covered", "Partly covered", "No matching work found")


def closest_ids(report: str, store: records.Store, n: int = 5) -> list[set[str]]:
    section = re.split(r"^## ", report, flags=re.M)
    body = next((s for s in section if s.lower().startswith("closest")), "")
    out: list[set[str]] = []
    for heading in re.findall(r"^### .*$", body, flags=re.M):
        for _, url, _ in verify.extract_links(heading):
            pair = ids.parse_id(url)
            if not pair:
                continue
            key = ids.id_str(*pair)
            rec = store.lookup(key)
            out.append(set(records.keys_of(rec)) | {key} if rec else {key})
            break
        if len(out) == n:
            break
    return out


def verdict_of(report: str) -> str | None:
    m = re.search(r"^## Verdict:\s*(.+)$", report, flags=re.M)
    if not m:
        return None
    text = m.group(1).strip().strip("*")
    return next((v for v in VERDICTS if v.lower() in text.lower()), text)


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    name, run = sys.argv[1], os.path.abspath(sys.argv[2])
    with open(os.path.join(HERE, "expected.json"), encoding="utf-8") as f:
        case = json.load(f)[name]
    with open(os.path.join(run, "report.md"), encoding="utf-8") as f:
        report = f.read()
    store = records.Store(os.path.join(run, "records.jsonl"))
    top = closest_ids(report, store)
    verdict = verdict_of(report)
    found_at = next((i + 1 for i, keys in enumerate(top) if keys & set(case["expect_any"])), None)
    paper_ok = not case["expect_any"] or found_at is not None
    verdict_ok = verdict in case["verdicts"]
    print("eval:     %s (%s)" % (name, case["paper"]))
    print("verdict:  %s -> %s" % (verdict, "ok" if verdict_ok else "UNEXPECTED"))
    if case["expect_any"]:
        print("expected: %s -> %s" % (", ".join(case["expect_any"]), "rank %d" % found_at if found_at else "NOT in top 5"))
    print("PASS" if paper_ok and verdict_ok else "FAIL")
    return 0 if paper_ok and verdict_ok else 1


if __name__ == "__main__":
    sys.exit(main())
