"""Shared test setup: isolated config/cache directories and canned HTTP answers."""

from __future__ import annotations

import os
import re
import shutil
import tempfile
import unittest
from unittest import mock

from novelty_check import keys, net, util

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fixture(name: str) -> str:
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return f.read()


class IsolatedTest(unittest.TestCase):
    """Each test gets empty config and cache directories and no API keys from the environment."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="novelty-check-test-")
        env = {
            "XDG_CACHE_HOME": os.path.join(self.tmp, "cache"),
            "XDG_CONFIG_HOME": os.path.join(self.tmp, "config"),
            "HOME": self.tmp,
        }
        self.env_patch = mock.patch.dict(os.environ, env)
        self.env_patch.start()
        for name in (
            "S2_API_KEY",
            "SEMANTIC_SCHOLAR_API_KEY",
            "OPENALEX_API_KEY",
            "NOVELTY_CHECK_CACHE",
            "NOVELTY_CHECK_RUN",
            "NOVELTY_CHECK_S2_KEYLESS",
        ):
            os.environ.pop(name, None)
        util.reset_cache_dir()
        keys.reset()
        # Throttling would only slow the tests down.
        self.throttle_patch = mock.patch.object(net, "throttle", lambda source: None)
        self.throttle_patch.start()

    def tearDown(self):
        self.throttle_patch.stop()
        self.env_patch.stop()
        util.reset_cache_dir()
        keys.reset()
        shutil.rmtree(self.tmp, ignore_errors=True)


class FakeHttp:
    """Replace net.fetch: answers come from (url regex, status, body) routes; calls are recorded."""

    def __init__(self, routes):
        self.routes = [(re.compile(p), status, body) for p, status, body in routes]
        self.calls = []

    def __call__(self, source, url, params=None, headers=None, method="GET", data=None, **kw):
        full = net._build_url(url, params)
        self.calls.append({"source": source, "url": full, "headers": headers or {}, "method": method})
        for pattern, status, body in self.routes:
            if pattern.search(full):
                return net.Response(status, body)
        return net.Response(404, "not found")

    def patch(self):
        return mock.patch.object(net, "fetch", self)
