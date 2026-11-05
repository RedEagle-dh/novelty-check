import unittest

from novelty_check import doctor


def report(s2_key=True, **states):
    sources = {n: {"state": "ok", "detail": ""} for n in ("s2", "openalex", "arxiv", "dblp", "openreview", "doi.org")}
    for name, state in states.items():
        sources[name.replace("_", ".")]["state"] = state
    return {"sources": sources, "keys": {"s2": {"present": s2_key}, "openalex": {"present": True}}}


class DecideModeTest(unittest.TestCase):
    def test_full(self):
        self.assertEqual(doctor.decide_mode(report())[0], "full")

    def test_rate_limited_key_is_still_full(self):
        mode, reason = doctor.decide_mode(report(s2="limited"))
        self.assertEqual(mode, "full")
        self.assertIn("too many requests", reason)

    def test_reduced_reasons(self):
        cases = {
            "No Semantic Scholar key": report(s2_key=False),
            "rejected the key": report(s2="rejected"),
            "can't be reached": report(s2="failed"),
        }
        for words, r in cases.items():
            with self.subTest(words=words):
                mode, reason = doctor.decide_mode(r)
                self.assertEqual(mode, "reduced")
                self.assertIn(words, reason)

    def test_blocked_and_partial_outage(self):
        offline = {n: "offline" for n in ("s2", "openalex", "arxiv", "dblp", "openreview", "doi_org")}
        self.assertEqual(doctor.decide_mode(report(**offline))[0], "blocked")
        mode, reason = doctor.decide_mode(report(dblp="offline"))
        self.assertEqual(mode, "full")
        self.assertIn("Not reachable right now: dblp", reason)


if __name__ == "__main__":
    unittest.main()
