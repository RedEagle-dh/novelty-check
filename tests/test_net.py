import multiprocessing
import os
import time
import unittest
from unittest import mock

from novelty_check import net, util

from .support import IsolatedTest


def _take_slots(cache_dir, n, out):
    os.environ["NOVELTY_CHECK_CACHE"] = cache_dir
    util.reset_cache_dir()
    for _ in range(n):
        net.throttle("test-source")
        out.append(time.time())


class CacheKeyTest(unittest.TestCase):
    def test_api_keys_do_not_change_the_cache_key(self):
        a = net._cache_key("GET", "https://api.openalex.org/works?search=x&api_key=AAA", {"x-api-key": "1"}, None)
        b = net._cache_key("GET", "https://api.openalex.org/works?api_key=BBB&search=x", {"x-api-key": "2"}, None)
        c = net._cache_key("GET", "https://api.openalex.org/works?search=y", {}, None)
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)


class CacheTest(IsolatedTest):
    def test_cached_answers_are_reused_and_never_contain_keys(self):
        calls = []

        class FakeResp:
            status = 200
            headers = {}

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b'{"ok": true}'

        def fake_urlopen(req, timeout=None):
            calls.append(req.full_url)
            return FakeResp()

        with mock.patch("urllib.request.urlopen", fake_urlopen):
            r1 = net.fetch("openalex", "https://api.openalex.org/works", params={"search": "x", "api_key": "SECRET"})
            r2 = net.fetch("openalex", "https://api.openalex.org/works", params={"search": "x", "api_key": "SECRET"})
        self.assertEqual(len(calls), 1)
        self.assertFalse(r1.cached)
        self.assertTrue(r2.cached)
        for root, _, files in os.walk(util.cache_dir()):
            for name in files:
                with open(os.path.join(root, name), encoding="utf-8", errors="replace") as f:
                    self.assertNotIn("SECRET", f.read())


class ThrottleTest(unittest.TestCase):
    def test_slots_are_spaced_across_processes(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d, mock.patch.dict(net.INTERVALS, {"test-source": 0.2}):
            ctx = multiprocessing.get_context("fork") if hasattr(os, "fork") else multiprocessing.get_context()
            with ctx.Manager() as manager:
                out = manager.list()
                procs = [ctx.Process(target=_take_slots, args=(d, 3, out)) for _ in range(2)]
                for p in procs:
                    p.start()
                for p in procs:
                    p.join(30)
                times = sorted(out)
        self.assertEqual(len(times), 6)
        gaps = [b - a for a, b in zip(times, times[1:])]
        self.assertGreaterEqual(min(gaps), 0.15, gaps)


if __name__ == "__main__":
    unittest.main()
