import os
import tempfile
import unittest

from novelty_check import records


def rec(source, ids_, title, **kw):
    return records.make(source, ids_, title, **kw)


class DedupTest(unittest.TestCase):
    def test_preprint_and_proceedings_merge_through_shared_id(self):
        preprint = rec(
            "arxiv",
            {"arxiv": "2309.06180"},
            "Efficient Memory Management for LLM Serving",
            year=2023,
            venue="arXiv",
            venue_type="preprint",
            abstract="short",
        )
        published = rec(
            "s2",
            {"doi": "10.1145/3600006.3613165", "arxiv": "2309.06180"},
            "Efficient Memory Management for LLM Serving",
            year=2023,
            venue="SOSP",
            venue_type="conference",
            abstract="a much longer abstract",
            citation_count=10,
        )
        merged = records.dedup([preprint, published])
        self.assertEqual(len(merged), 1)
        m = merged[0]
        self.assertEqual(m["id"], "doi:10.1145/3600006.3613165")
        self.assertEqual(m["venue"], "SOSP")
        self.assertEqual(m["venue_type"], "conference")
        self.assertEqual(m["abstract"], "a much longer abstract")
        self.assertEqual(m["found_in"], ["arxiv", "s2"])
        self.assertEqual(m["ids"]["arxiv"], "2309.06180")

    def test_same_title_within_a_year_merges(self):
        a = rec("dblp", {"dblp": "conf/x/A"}, "A Long Enough Title About Paged Caches", year=2023)
        b = rec("openalex", {"openalex": "W1"}, "A long enough title about paged caches.", year=2024)
        self.assertEqual(len(records.dedup([a, b])), 1)

    def test_same_title_years_apart_stays_separate(self):
        a = rec("dblp", {"dblp": "conf/x/A"}, "A Long Enough Title About Paged Caches", year=2015)
        b = rec("openalex", {"openalex": "W1"}, "A Long Enough Title About Paged Caches", year=2023)
        self.assertEqual(len(records.dedup([a, b])), 2)

    def test_short_generic_titles_are_not_matched(self):
        a = rec("dblp", {"dblp": "conf/x/A"}, "Introduction", year=2023)
        b = rec("dblp", {"dblp": "conf/y/B"}, "Introduction", year=2023)
        self.assertEqual(len(records.dedup([a, b])), 2)

    def test_annotations_merge(self):
        base = rec("s2", {"doi": "10.1/x"}, "Some Paper Title That Is Long Enough")
        a = dict(base, rating="low", claims=["C2"], angles=["a"], notes=[{"angle": "a", "text": "x"}])
        b = dict(base, rating="high", claims=["C1", "C10"], angles=["b"], notes=[{"angle": "b", "text": "y"}])
        m = records.dedup([a, b])[0]
        self.assertEqual(m["rating"], "high")
        self.assertEqual(m["claims"], ["C1", "C2", "C10"])
        self.assertEqual(m["angles"], ["a", "b"])
        self.assertEqual(len(m["notes"]), 2)

    def test_title_trailing_period_removed(self):
        self.assertEqual(rec("dblp", {"dblp": "k"}, "A Title.")["title"], "A Title")


class StoreTest(unittest.TestCase):
    def test_lookup_by_any_id(self):
        with tempfile.TemporaryDirectory() as d:
            store = records.Store(os.path.join(d, "records.jsonl"))
            store.add([rec("s2", {"doi": "10.1/x", "arxiv": "2401.00001", "s2": "a" * 40}, "Title Of Some Length Here")])
            store.add(
                [
                    rec(
                        "dblp",
                        {"dblp": "conf/x/Y", "doi": "10.1/x"},
                        "Title Of Some Length Here",
                        venue="ICSE",
                        venue_type="conference",
                    )
                ]
            )
            for key in ("doi:10.1/x", "arxiv:2401.00001", "https://arxiv.org/abs/2401.00001", "dblp:conf/x/Y"):
                with self.subTest(key=key):
                    found = store.lookup(key)
                    self.assertIsNotNone(found)
                    self.assertEqual(found["venue"], "ICSE")
            self.assertIsNone(store.lookup("doi:10.1/other"))


class BriefTest(unittest.TestCase):
    def test_brief_shows_essentials(self):
        r = rec(
            "s2",
            {"doi": "10.1/x"},
            "A Paper",
            year=2024,
            venue="ICSE",
            venue_type="conference",
            authors=["Ada Lovelace", "Hao Zhang 0025"],
            abstract="word " * 200,
            citation_count=3,
        )
        text = records.brief(r, 1, abstract_chars=50)
        self.assertIn("[1] doi:10.1/x", text)
        self.assertIn("ICSE (conference)", text)
        self.assertIn("Hao Zhang", text)
        self.assertNotIn("0025", text)
        self.assertIn("…", text)


if __name__ == "__main__":
    unittest.main()
