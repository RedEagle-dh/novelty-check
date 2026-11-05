"""One module per scholarly source. Each returns records built with `records.make`."""


class Skipped(Exception):
    """The source was deliberately not queried (for example, no API key)."""


DEFAULT_SOURCES = ("s2", "openalex", "arxiv", "dblp")
ALL_SOURCES = ("s2", "openalex", "arxiv", "dblp", "openreview")
LABELS = {
    "s2": "Semantic Scholar",
    "openalex": "OpenAlex",
    "arxiv": "arXiv",
    "dblp": "DBLP",
    "openreview": "OpenReview",
}
