import unittest

from novelty_check import ids


class ParseIdTest(unittest.TestCase):
    def test_prefixed_and_bare_forms(self):
        cases = {
            "doi:10.1145/3600006.3613165": ("doi", "10.1145/3600006.3613165"),
            "10.1145/3600006.3613165": ("doi", "10.1145/3600006.3613165"),
            "DOI:10.1145/ABC.Def": ("doi", "10.1145/abc.def"),
            "arxiv:2309.06180v2": ("arxiv", "2309.06180"),
            "2309.06180": ("arxiv", "2309.06180"),
            "arXiv:cs/0112017v1": ("arxiv", "cs/0112017"),
            "W4387321091": ("openalex", "W4387321091"),
            "83b90f4a0ae4cc214eb3cc140ccfef9cd99fac05": ("s2", "83b90f4a0ae4cc214eb3cc140ccfef9cd99fac05"),
            "dblp:conf/sosp/KwonLZ0ZY0ZS23": ("dblp", "conf/sosp/KwonLZ0ZY0ZS23"),
            "openreview:J28Jfjqb4P": ("openreview", "J28Jfjqb4P"),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(ids.parse_id(text), expected)

    def test_urls(self):
        cases = {
            "https://doi.org/10.1145/3600006.3613165": ("doi", "10.1145/3600006.3613165"),
            "http://dx.doi.org/10.1145/3600006.3613165": ("doi", "10.1145/3600006.3613165"),
            "https://arxiv.org/abs/2309.06180v1": ("arxiv", "2309.06180"),
            "https://arxiv.org/pdf/2309.06180.pdf": ("arxiv", "2309.06180"),
            "https://arxiv.org/html/2309.06180": ("arxiv", "2309.06180"),
            "https://openreview.net/forum?id=J28Jfjqb4P": ("openreview", "J28Jfjqb4P"),
            "https://dblp.org/rec/conf/sosp/KwonLZ0ZY0ZS23.html": ("dblp", "conf/sosp/KwonLZ0ZY0ZS23"),
            "https://www.semanticscholar.org/paper/Efficient/83b90f4a0ae4cc214eb3cc140ccfef9cd99fac05": (
                "s2",
                "83b90f4a0ae4cc214eb3cc140ccfef9cd99fac05",
            ),
            "https://openalex.org/W4387321091": ("openalex", "W4387321091"),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(ids.parse_id(text), expected)

    def test_arxiv_doi_becomes_arxiv_id(self):
        self.assertEqual(ids.parse_id("https://doi.org/10.48550/arXiv.2309.06180"), ("arxiv", "2309.06180"))
        self.assertEqual(ids.parse_id("10.48550/ARXIV.2309.06180"), ("arxiv", "2309.06180"))

    def test_unrecognised(self):
        for text in ("https://blog.vllm.ai/2023/06/20/vllm.html", "hello world", "https://arxiv.org/list/cs.LG/recent"):
            with self.subTest(text=text):
                self.assertIsNone(ids.parse_id(text))

    def test_canonical_priority_and_urls(self):
        both = {"arxiv": "2309.06180", "doi": "10.1145/3600006.3613165", "dblp": "conf/sosp/X"}
        self.assertEqual(ids.canonical(both), "doi:10.1145/3600006.3613165")
        self.assertEqual(ids.record_url(both), "https://doi.org/10.1145/3600006.3613165")
        self.assertEqual(ids.record_url({"openreview": "abc"}), "https://openreview.net/forum?id=abc")


if __name__ == "__main__":
    unittest.main()
