import unittest

from novelty_check import bib, records

from .support import FakeHttp, IsolatedTest

CROSSREF = (
    "@inproceedings{Kwon_2023, series={SOSP ’23}, title={Efficient Memory Management for Large Language Model "
    "Serving with PagedAttention}, url={http://dx.doi.org/10.1145/3600006.3613165}, DOI={10.1145/3600006.3613165}, "
    "booktitle={Proceedings of the 29th Symposium on Operating Systems Principles}, publisher={ACM}, "
    "author={Kwon, Woosuk and Li, Zhuohan}, year={2023}, month=Oct, pages={611–626} }"
)


def rec(**kw):
    base = dict(
        source="dblp",
        ids_={"dblp": "conf/x/Y"},
        title="Towards the Paging of Caches",
        authors=["Hao Zhang 0025"],
        year=2023,
        venue="ICSE",
        venue_type="conference",
    )
    base.update(kw)
    return records.make(base.pop("source"), base.pop("ids_"), base.pop("title"), **base)


class KeyTest(unittest.TestCase):
    def test_cite_key(self):
        self.assertEqual(bib.cite_key(rec()), "zhang2023paging")
        self.assertEqual(bib.cite_key(rec(authors=["(anonymous while under review)"])), "anon2023paging")

    def test_unique_keys(self):
        self.assertEqual(bib.unique_keys([rec(), rec(), rec()]), ["zhang2023paging", "zhang2023paginga", "zhang2023pagingb"])


class EntryTest(IsolatedTest):
    def test_doi_entry_is_rekeyed_and_pretty(self):
        fake = FakeHttp([(r"doi\.org/10\.1145", 200, CROSSREF)])
        with fake.patch():
            entry, origin = bib.entry_for(rec(ids_={"doi": "10.1145/3600006.3613165"}), "kwon2023efficient")
        self.assertTrue(entry.startswith("@inproceedings{kwon2023efficient,\n"))
        self.assertIn("\n  title={Efficient Memory Management", entry)
        self.assertTrue(entry.endswith("\n}"))
        self.assertIn("doi.org", origin)
        self.assertEqual(fake.calls[0]["headers"]["Accept"], "application/x-bibtex; charset=utf-8")

    def test_metadata_fallback(self):
        fake = FakeHttp([])
        with fake.patch():
            entry, origin = bib.entry_for(rec(title="Caches & Pages_now"), "k")
        self.assertEqual(origin, "generated from metadata")
        self.assertIn("@inproceedings{k,", entry)
        self.assertIn("booktitle = {ICSE}", entry)
        self.assertIn("Caches \\& Pages\\_now", entry)
        self.assertIn("url = {https://dblp.org/rec/conf/x/Y}", entry)


if __name__ == "__main__":
    unittest.main()
