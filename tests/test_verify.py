import json
import os
import unittest

from novelty_check import records, verify

from .support import FakeHttp, IsolatedTest, fixture

REPORT = """# Report
1. [Efficient Memory Management for Large Language Model Serving with PagedAttention](https://doi.org/10.1145/3600006.3613165)
2. [Quantum bananas in operating system kernels for everyone](https://doi.org/10.1145/3600006.3613165)
3. A blog post: https://blog.vllm.ai/2023/06/20/vllm.html.
4. [A list page](https://arxiv.org/list/cs.LG/recent)
5. [Fake](https://doi.org/10.9999/does-not-exist)
6. [AB-Sparse](https://openreview.net/forum?id=J28Jfjqb4P) and [missing](https://openreview.net/forum?id=nope)
"""


class ExtractTest(unittest.TestCase):
    def test_extract_links(self):
        links = verify.extract_links(REPORT)
        urls = [u for _, u, _ in links]
        self.assertIn("https://blog.vllm.ai/2023/06/20/vllm.html", urls)
        self.assertEqual(urls.count("https://doi.org/10.1145/3600006.3613165"), 2)
        self.assertEqual(len(links), 7)


class CheckTest(IsolatedTest):
    def test_check(self):
        s2_paper = fixture("s2_paper.json")
        fake = FakeHttp(
            [
                (r"semanticscholar\.org/graph/v1/paper/DOI:10\.1145", 200, s2_paper),
            ]
        )
        store = records.Store(os.path.join(self.tmp, "records.jsonl"))
        note = json.loads(fixture("openreview_search.json"))["notes"][-1]
        from novelty_check.sources import openreview

        store.add([openreview.to_record(note)])
        with fake.patch():
            result = verify.check(REPORT, store)
        by_line = {}
        for r in result["results"]:
            by_line.setdefault(r["line"], []).append(r)
        self.assertEqual(by_line[2][0]["status"], "ok")
        self.assertEqual(by_line[3][0]["status"], "warning")  # wrong title for a real DOI
        self.assertEqual(by_line[4][0]["status"], "error")  # blog
        self.assertEqual(by_line[5][0]["status"], "error")  # not a paper record
        self.assertEqual(by_line[6][0]["status"], "error")  # unknown DOI
        self.assertEqual([r["status"] for r in by_line[7]], ["ok", "error"])
        self.assertEqual(result["summary"]["errors"], 4)
        self.assertEqual(result["summary"]["warnings"], 1)


if __name__ == "__main__":
    unittest.main()
