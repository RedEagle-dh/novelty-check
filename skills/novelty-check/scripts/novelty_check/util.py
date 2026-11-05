"""Small helpers: directories, text normalisation, timestamps, file locking."""

from __future__ import annotations

import contextlib
import datetime
import os
import re
import sys
import unicodedata

try:  # POSIX only; the skill targets Linux and macOS.
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]

APP = "novelty-check"
_cache_dir: str | None = None


def config_dir() -> str:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, APP)


def _writable_dir(path: str) -> bool:
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".write-test-%d" % os.getpid())
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
        return True
    except OSError:
        return False


def cache_dir_candidates() -> list[str]:
    candidates = []
    if os.environ.get("NOVELTY_CHECK_CACHE"):
        candidates.append(os.environ["NOVELTY_CHECK_CACHE"])
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    candidates.append(os.path.join(base, APP))
    # Sandboxed agents (e.g. Codex) may only allow writes in the working directory.
    candidates.append(os.path.join(os.getcwd(), ".novelty-check-cache"))
    return candidates


def cache_dir() -> str:
    global _cache_dir
    if _cache_dir:
        return _cache_dir
    candidates = cache_dir_candidates()
    for c in candidates:
        if _writable_dir(c):
            _cache_dir = c
            return c
    raise SystemExit("novelty-check: no writable cache directory (tried: %s)" % ", ".join(candidates))


def reset_cache_dir() -> None:
    """For tests: forget the memoised cache directory."""
    global _cache_dir
    _cache_dir = None


def norm_space(s: str | None) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def fold_ascii(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(ch for ch in s if not unicodedata.combining(ch))


def norm_title(s: str | None) -> str:
    s = fold_ascii(s or "").lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return s.strip()


def slugify(s: str, maxlen: int = 50) -> str:
    s = norm_title(s).replace(" ", "-")
    s = s[:maxlen].rstrip("-")
    return s or "idea"


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today() -> str:
    return datetime.date.today().isoformat()


def eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


@contextlib.contextmanager
def locked(path: str):
    """Exclusive advisory lock on `path` (created if missing), shared across processes."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        if fcntl is not None:
            fcntl.flock(fd, fcntl.LOCK_EX)
        yield fd
    finally:
        if fcntl is not None:
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def append_lines(path: str, lines: list[str]) -> None:
    """Append text lines to a file while holding a lock, so parallel writers don't interleave."""
    if not lines:
        return
    folder, name = os.path.split(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    with locked(os.path.join(folder, "." + name + ".lock")), open(path, "a", encoding="utf-8") as f:
        for line in lines:
            f.write(line.rstrip("\n") + "\n")


STOPWORDS = frozenset(
    """a an the of for in on with and or to via using use by from at as is are be into onto over under
    based towards toward through about this that these those its it we our their than then new novel
    approach method methods study""".split()
)
