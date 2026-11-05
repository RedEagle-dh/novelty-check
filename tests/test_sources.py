"""Parsing of recorded answers from each source (tests/fixtures, recorded 2026-11-05)."""

import json
import os
import unittest

from novelty_check import keys
from novelty_check.sources import Skipped, arxiv, dblp, openalex, openreview, s2

from .support import FakeHttp, IsolatedTest, fixture


class S2Test(IsolatedTest):
    def test_paper_record(self):
        r = s2.to_record(json.loads(fixture("s2_paper.json")))
        self.assertEqual(r["id"], "doi:10.1145/3600006.3613165")
        self.assertEqual(r["ids"]["arxiv"], "2309.06180")
        self.assertEqual(r["ids"]["dblp"], "conf/sosp/KwonLZ0ZY0ZS23")
        self.assertEqual(r["venue_type"], "conference")
        self.assertTrue(r["abstract"])

    def test_search_skipped_without_key(self):
        with self.assertRaises(Skipped):
            s2.search("paged attention")

    def test_search_sends_key_and_parses(self):
        os.environ["S2_API_KEY"] = "secret-test-key"
        keys.reset()
        body = json.dumps({"total": 1, "offset": 0, "data": [json.loads(fixture("s2_paper.json"))]})
        fake = FakeHttp([(r"paper/search", 200, body)])
        with fake.patch():
            recs, total = s2.search("retrieval-augmented generation", limit=5, year_from=2020)
        self.assertEqual(total, 1)
        self.assertEqual(recs[0]["title"], "Efficient Memory Management for Large Language Model Serving with PagedAttention")
        call = fake.calls[0]
        self.assertEqual(call["headers"]["x-api-key"], "secret-test-key")
        self.assertIn("query=retrieval+augmented+generation", call["url"])
        self.assertIn("year=2020-", call["url"])

    def test_references(self):
        fake = FakeHttp([(r"/references", 200, fixture("s2_references.json"))])
        with fake.patch():
            recs = s2.expand("arxiv", "2309.06180", "references", 3)
        self.assertTrue(recs)
        self.assertTrue(all(r["id"] for r in recs))
        self.assertIn("ARXIV:2309.06180", fake.calls[0]["url"])


class OpenAlexTest(IsolatedTest):
    def test_work_record(self):
        r = openalex.to_record(json.loads(fixture("openalex_work.json")))
        self.assertEqual(r["ids"]["openalex"], "W4387321091")
        self.assertEqual(r["id"], "doi:10.1145/3600006.3613165")
        self.assertEqual(r["venue_type"], "conference")
        self.assertTrue(r["abstract"].startswith("High throughput serving"))
        self.assertEqual(r["authors"][0], "Woosuk Kwon")

    def test_rebuild_abstract(self):
        self.assertEqual(openalex.rebuild_abstract({"world": [1], "hello": [0], "again": [2]}), "hello world again")
        self.assertIsNone(openalex.rebuild_abstract(None))

    def test_search_params_and_key(self):
        os.environ["OPENALEX_API_KEY"] = "oa-key"
        keys.reset()
        body = json.dumps({"meta": {"count": 1}, "results": [json.loads(fixture("openalex_work.json"))]})
        fake = FakeHttp([(r"/works\?", 200, body)])
        with fake.patch():
            recs, total = openalex.search("paged attention", limit=3, year_from=2022)
        url = fake.calls[0]["url"]
        self.assertIn("api_key=oa-key", url)
        self.assertIn("primary_topic.domain.id%3Adomains%2F3", url)
        self.assertIn("from_publication_date%3A2022-01-01", url)
        self.assertEqual(total, 1)
        self.assertEqual(len(recs), 1)


class ArxivTest(IsolatedTest):
    def test_parse_feed(self):
        recs, total = arxiv.parse_feed(fixture("arxiv_query.xml"))
        self.assertEqual(total, 2)
        ids_ = {r["ids"]["arxiv"] for r in recs}
        self.assertEqual(ids_, {"2309.06180", "2305.18290"})
        for r in recs:
            self.assertEqual(r["venue_type"], "preprint")
            self.assertTrue(r["abstract"])
            self.assertTrue(r["fulltext_url"].startswith("https://arxiv.org/html/"))

    def test_build_query(self):
        q = arxiv.build_query('paged "key value" cache for serving', 2020, None)
        self.assertIn('all:"key value"', q)
        self.assertIn("all:paged AND", q)
        self.assertNotIn("all:for", q)
        self.assertIn("cat:cs.*", q)
        self.assertIn("submittedDate:[202001010000 TO 209912312359]", q)
        self.assertEqual(arxiv.build_query("ti:vllm"), "ti:vllm")


class DblpTest(IsolatedTest):
    def test_search_parsing_and_order(self):
        fake = FakeHttp([(r"sparql", 200, fixture("dblp_search.json"))])
        with fake.patch():
            recs, total = dblp.search("PagedAttention", limit=10)
        self.assertEqual(total, 6)
        sosp = next(r for r in recs if r["ids"].get("dblp") == "conf/sosp/KwonLZ0ZY0ZS23")
        self.assertEqual(sosp["authors"][0], "Woosuk Kwon")
        self.assertIn("Hao Zhang", sosp["authors"])
        self.assertEqual(sosp["venue_type"], "conference")
        corr = next(r for r in recs if r["ids"].get("arxiv") == "2309.06180")
        self.assertEqual(corr["venue"], "arXiv")
        self.assertEqual(corr["venue_type"], "preprint")
        # Published work is listed before preprints.
        kinds = [r["venue_type"] == "preprint" for r in recs]
        self.assertEqual(kinds, sorted(kinds))

    def test_words(self):
        self.assertEqual(
            dblp.words("Retrieval-Augmented Generation for the code*"), ["retrieval", "augmented", "generation", "code*"]
        )

    def test_query_keeps_only_words(self):
        q = dblp.build_search('say "hi" there } INSERT')
        self.assertIn('ql:contains-word "say hi there insert"', q)


class OpenReviewTest(IsolatedTest):
    def test_imported_records_are_dropped(self):
        notes = json.loads(fixture("openreview_search.json"))["notes"]
        recs = [r for r in (openreview.to_record(n) for n in notes) if r]
        self.assertEqual([r["ids"]["openreview"] for r in recs], ["J28Jfjqb4P"])
        r = recs[0]
        self.assertEqual(r["venue_type"], "submission")
        self.assertEqual(r["status"], "submitted, not accepted (yet)")
        self.assertEqual(r["year"], 2027)
        self.assertTrue(r["bibtex"].startswith("@"))


if __name__ == "__main__":
    unittest.main()
