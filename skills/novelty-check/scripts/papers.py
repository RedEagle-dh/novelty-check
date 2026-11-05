"""Entry point for the novelty-check search tool. Prefer the `papers` shell wrapper next to this file."""

import os
import sys

if sys.version_info < (3, 9):
    sys.exit("novelty-check needs Python 3.9 or later (found %s)" % sys.version.split()[0])

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from novelty_check.cli import main  # noqa: E402

if __name__ == "__main__":
    try:
        code = main()
        sys.stdout.flush()
    except BrokenPipeError:  # output piped into `head` and the like
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        code = 0
    sys.exit(code)
