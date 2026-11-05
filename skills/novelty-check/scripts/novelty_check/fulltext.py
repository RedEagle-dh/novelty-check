"""Readable full text: arXiv HTML first, then open-access PDFs (via pdftotext if installed)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from html.parser import HTMLParser

from . import net, util

SKIP_TAGS = {"script", "style", "nav", "header", "footer", "button", "svg", "noscript", "form"}
BLOCK_TAGS = {"p", "div", "section", "article", "li", "tr", "br", "figcaption", "table", "blockquote", "dd", "dt", "caption"}


class _Extractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0
        self.in_math = 0
        self.heading: int | None = None
        self.headings: list[str] = []
        self._heading_buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class") or ""
        if tag in SKIP_TAGS or "ltx_page_footer" in cls or "ltx_page_header" in cls:
            self.skip += 1
            return
        if tag == "math":
            self.in_math += 1
            alt = a.get("alttext")
            if alt and not self.skip:
                self.parts.append(" %s " % alt)
            return
        m = re.match(r"^h([1-6])$", tag)
        if m and not self.skip:
            self.heading = int(m.group(1))
            self._heading_buf = []
            self.parts.append("\n\n" + "#" * self.heading + " ")
        elif tag in BLOCK_TAGS and not self.skip:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS:
            self.skip = max(0, self.skip - 1)
            return
        if tag == "math":
            self.in_math = max(0, self.in_math - 1)
            return
        if re.match(r"^h[1-6]$", tag) and self.heading is not None:
            text = util.norm_space("".join(self._heading_buf))
            if text:
                self.headings.append("#" * self.heading + " " + text)
            self.heading = None
            self.parts.append("\n")
        elif tag in BLOCK_TAGS and not self.skip:
            self.parts.append("\n")

    def handle_data(self, data):
        if self.skip or self.in_math:
            return
        self.parts.append(data)
        if self.heading is not None:
            self._heading_buf.append(data)

    def text(self) -> str:
        raw = "".join(self.parts)
        raw = re.sub(r"[ \t ]+", " ", raw)
        raw = re.sub(r" *\n *", "\n", raw)
        return re.sub(r"\n{3,}", "\n\n", raw).strip() + "\n"


def html_to_text(html: str) -> tuple[str, list[str]]:
    p = _Extractor()
    p.feed(html)
    p.close()
    return p.text(), p.headings


def _safe_name(idstr: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", idstr)


def fetch(rec: dict, out_dir: str) -> dict:
    """Save full text for a record. Returns {path, kind, chars, headings} or {error, tried}."""
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.join(out_dir, _safe_name(rec["id"]))
    tried = []
    arxiv_id = rec.get("ids", {}).get("arxiv")
    if arxiv_id:
        url = "https://arxiv.org/html/" + arxiv_id
        tried.append(url)
        try:
            resp = net.fetch("arxiv-web", url, retries=1)
            if resp.status == 200 and "ltx_document" in resp.text:
                text, headings = html_to_text(resp.text)
                return _save(base + ".txt", text, "arXiv HTML", url, headings)
        except net.SourceError:
            pass
    pdf_urls = []
    if arxiv_id:
        pdf_urls.append("https://arxiv.org/pdf/" + arxiv_id)
    if rec.get("fulltext_url") and rec["fulltext_url"] not in pdf_urls and "/html/" not in rec["fulltext_url"]:
        pdf_urls.append(rec["fulltext_url"])
    for url in pdf_urls:
        tried.append(url)
        pdf_path = base + ".pdf"
        try:
            ctype = net.download("fulltext", url, pdf_path)
        except net.SourceError:
            continue
        with open(pdf_path, "rb") as f:
            if f.read(5) != b"%PDF-":
                os.remove(pdf_path)
                continue
        tool = shutil.which("pdftotext")
        if tool:
            txt_path = base + ".txt"
            try:
                subprocess.run([tool, "-enc", "UTF-8", pdf_path, txt_path], check=True, capture_output=True, timeout=120)
                with open(txt_path, encoding="utf-8", errors="replace") as f:
                    text = f.read()
                return _save(txt_path, text, "PDF via pdftotext", url, _guess_pdf_headings(text))
            except (subprocess.SubprocessError, OSError):
                pass
        return {
            "path": pdf_path,
            "kind": "PDF (no text extracted)",
            "source_url": url,
            "content_type": ctype,
            "hint": "pdftotext is not installed. Read the PDF directly if you can, or install poppler "
            "(nix shell nixpkgs#poppler_utils / brew install poppler / apt install poppler-utils).",
        }
    return {"error": "no full text available; judge on the abstract", "tried": tried}


def _guess_pdf_headings(text: str) -> list[str]:
    out = []
    for line in text.splitlines():
        line = line.strip()
        if re.match(r"^(\d+(\.\d+)*\.?|[IVX]+\.)\s+[A-Z][A-Za-z ,:\-]{2,60}$", line):
            out.append(line)
    return out[:60]


def _save(path: str, text: str, kind: str, url: str, headings: list[str]) -> dict:
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return {"path": path, "kind": kind, "source_url": url, "chars": len(text), "headings": headings[:60]}
