import contextlib
import io
import json
import os

from novelty_check import cli, records

from .support import FakeHttp, IsolatedTest, fixture


def run(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = cli.main(list(argv))
    return code, out.getvalue()


class InitRunTest(IsolatedTest):
    def test_creates_folders_and_never_reuses_one(self):
        code, out = run("init-run", "--title", "Paged KV Cache für LLMs", "--base", self.tmp)
        self.assertEqual(code, 0)
        first = out.strip()
        self.assertTrue(first.endswith("-paged-kv-cache-fur-llms"))
        for sub in ("notes", "candidates", "assessments", "fulltext"):
            self.assertTrue(os.path.isdir(os.path.join(first, sub)))
        _, out2 = run("init-run", "--title", "Paged KV Cache für LLMs", "--base", self.tmp)
        self.assertEqual(out2.strip(), first + "-2")


class SearchFlowTest(IsolatedTest):
    def setUp(self):
        super().setUp()
        _, out = run("init-run", "--title", "flow", "--base", self.tmp)
        self.run_dir = out.strip()
        self.fake = FakeHttp(
            [
                (r"sparql\.dblp\.org", 200, fixture("dblp_search.json")),
                (r"export\.arxiv\.org", 200, fixture("arxiv_query.xml")),
                (r"semanticscholar\.org/graph/v1/paper/DOI", 200, fixture("s2_paper.json")),
            ]
        )

    def test_search_logs_skips_and_stores_records(self):
        with self.fake.patch():
            code, out = run(
                "search", "-q", "paged attention", "--source", "s2,dblp,arxiv", "--run", self.run_dir, "--angle", "method"
            )
        self.assertEqual(code, 0)
        self.assertIn("Semantic Scholar skipped", out)
        self.assertIn("DBLP 6 of 6", out)
        log = records.read_jsonl(os.path.join(self.run_dir, "search-log.jsonl"))
        self.assertEqual([e["source"] for e in log], ["s2", "dblp", "arxiv"])
        self.assertEqual(log[0]["status"], "skipped")
        self.assertTrue(all(e["angle"] == "method" for e in log))
        # The arXiv and DBLP copies of the same paper were merged.
        self.assertEqual(out.count("arxiv:2309.06180  "), 0)
        stored = records.read_jsonl(os.path.join(self.run_dir, "records.jsonl"))
        self.assertTrue(stored)

    def test_mark_merge_and_log_summary(self):
        with self.fake.patch():
            run("search", "-q", "paged attention", "--source", "dblp", "--run", self.run_dir, "--angle", "method")
            cand = os.path.join(self.run_dir, "candidates", "method.jsonl")
            code, _ = run(
                "mark",
                "dblp:conf/sosp/KwonLZ0ZY0ZS23",
                "--to",
                cand,
                "--rating",
                "high",
                "--claims",
                "C1,C2",
                "--note",
                "same idea",
                "--run",
                self.run_dir,
                "--angle",
                "method",
            )
            self.assertEqual(code, 0)
            run(
                "mark",
                "arxiv:2309.06180",
                "--to",
                os.path.join(self.run_dir, "candidates", "vocab.jsonl"),
                "--rating",
                "medium",
                "--claims",
                "C3",
                "--run",
                self.run_dir,
                "--angle",
                "vocab",
            )
        out_file = os.path.join(self.run_dir, "candidates.jsonl")
        code, out = run(
            "merge", cand, os.path.join(self.run_dir, "candidates", "vocab.jsonl"), "--out", out_file, "--run", self.run_dir
        )
        self.assertEqual(code, 0)
        merged = records.read_jsonl(out_file)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["rating"], "high")
        self.assertEqual(merged[0]["claims"], ["C1", "C2", "C3"])
        self.assertEqual(merged[0]["angles"], ["method", "vocab"])
        code, summary = run("log-summary", "--run", self.run_dir)
        self.assertIn("| Query | DBLP |", summary)
        self.assertIn("| paged attention | 6 |", summary)

    def test_mark_rejects_bad_claims(self):
        with self.fake.patch():
            run("search", "-q", "paged attention", "--source", "dblp", "--run", self.run_dir)
            with self.assertRaises(SystemExit):
                run(
                    "mark",
                    "dblp:conf/sosp/KwonLZ0ZY0ZS23",
                    "--to",
                    os.path.join(self.tmp, "x.jsonl"),
                    "--rating",
                    "high",
                    "--claims",
                    "the whole thing",
                    "--run",
                    self.run_dir,
                )

    def test_get_fills_abstract_for_dblp_hit(self):
        with self.fake.patch():
            run("search", "-q", "paged attention", "--source", "dblp", "--run", self.run_dir)
            code, out = run("get", "dblp:conf/sosp/KwonLZ0ZY0ZS23", "--run", self.run_dir, "--format", "jsonl")
        self.assertEqual(code, 0)
        rec = json.loads(out.strip().splitlines()[0])
        self.assertTrue(rec["abstract"])
        self.assertEqual(rec["id"], "doi:10.1145/3600006.3613165")
