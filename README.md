# novelty-check

An agent skill that checks whether a computer-science research idea has already been done.

You describe the idea. The agent splits it into claims, searches Semantic Scholar, DBLP, arXiv,
OpenAlex and (for ML) OpenReview in parallel, follows citations from the closest hits, reads the
closest papers and writes a report:

- a verdict: **Already done**, **Largely covered**, **Partly covered** or **No matching work found**,
- the closest existing works, each with what it covers and what it doesn't,
- a table of your claims against those works,
- what is still open, i.e. where your contribution could be,
- a log of every query, so you can show how you checked,
- BibTeX for every cited work.

Only scholarly records count as evidence: every cited work resolves to a DOI, arXiv ID, DBLP key,
Semantic Scholar ID or OpenReview ID, and a built-in check rejects any other link before the
report is handed over. Web pages, blogs and news never appear as sources.

## Install

```sh
npx skills add RedEagle-dh/novelty-check
```

Pick your agent when asked (Claude Code, Codex, OpenCode, Hermes Agent, Command Code and others
work). Update later with `npx skills update`.

**Requirements:** Python 3.9 or later, nothing else to install.

- macOS: the system `python3` from the Xcode Command Line Tools is enough (`xcode-select --install`).
- NixOS: if `python3` is not on your PATH, the skill runs it through `nix run nixpkgs#python3`.
- Optional: `pdftotext` (poppler) lets the agent read PDFs that are not on arXiv.

## API keys (one set per person)

Get your own keys; don't share them. Colleagues on the same university network share one public
IP address, and without keys everyone on it shares the same small free limits.

| Source | Key | Without it |
|---|---|---|
| Semantic Scholar | Free, [request form](https://www.semanticscholar.org/product/api#api-key-form). Approval can take a few days. | Keyword search is off ("reduced mode"); citation following still works. |
| OpenAlex | Free, [account settings](https://openalex.org/settings/api) | About 100 searches a day for your whole network. |
| DBLP, arXiv, OpenReview | none needed | |

Store the keys by running this **in your own terminal** (input is hidden), not through the agent:

```sh
sh ~/.agents/skills/novelty-check/scripts/papers setup    # path depends on your agent, see below
```

Or set `S2_API_KEY` and `OPENALEX_API_KEY` in your environment (e.g. through your secrets manager
or Nix config). Keys are kept in `~/.config/novelty-check/keys.json` (mode 600) and never written
into reports, logs or the cache.

Check everything with `sh <skill dir>/scripts/papers doctor`. The skill directory is wherever
`npx skills add` put it, for example `~/.agents/skills/novelty-check`,
`~/.claude/skills/novelty-check` or `~/.codex/skills/novelty-check`.

## Use

Ask your agent in plain words, in English or German:

> Has this been done? I want to use eBPF traces to predict thermal throttling on Raspberry Pi
> clusters and move CI jobs to cooler boards before it happens.

> Gibt es dazu schon Arbeiten? Meine Idee: …

Or point it at a file: "Run a novelty check on `docs/exposé.md`."

The agent first shows you how it split the idea into claims and asks you to correct them. That
matters: the search and the verdict are only as good as the claims. A run then takes about
20–30 minutes.

Results go to `novelty-checks/<date>-<title>/` in the current directory. Earlier runs are never
overwritten.

| File | Contents |
|---|---|
| `report.md` | The report |
| `references.bib` | BibTeX for every work in the report |
| `idea.md` | Your idea as checked, with claims C1…Cn |
| `search-log.jsonl` | Every query: source, time, hits, errors |
| `notes/`, `assessments/` | What each searcher found; claim-by-claim judgements with quotes |

## Agents

| Agent | Parallel subagents | Notes |
|---|---|---|
| Claude Code | yes (Agent tool) | |
| Codex | yes (`spawn_agent`) | The default sandbox blocks network access. Allow it in `~/.codex/config.toml`: `[sandbox_workspace_write]` with `network_access = true`. |
| OpenCode | yes (Task tool) | |
| Hermes Agent, Command Code, others | if the agent has a subagent tool | Otherwise the agent runs the same steps one after another: slower, same result. |

## Privacy

Only short keyword queries and paper IDs are sent to the paper databases; your idea's text stays
in the run folder. Your agent's model provider (Anthropic, OpenAI, DeepSeek, …) does see the
idea, as with anything you type into the agent.

## Limits

- It searches the databases above. A paper that none of them index, or that is only in a
  paywalled full text, can be missed. "No matching work found" is a statement about these
  sources on that date, not a proof.
- Google Scholar is not used: it has no API and blocks automated access.
- Overlap is judged from abstracts and, where available, full texts from arXiv or open-access
  PDFs. The report says which, for every paper.
- It is built for computer science. Other fields would need other sources.

## The search tool

The skill drives `scripts/papers`, a small Python program using only the standard library. You
can use it directly:

```sh
P="sh ~/.agents/skills/novelty-check/scripts/papers"
$P doctor
$P search -q "paged kv cache serving" --source default,openreview
$P get 10.1145/3600006.3613165
$P expand arxiv:2309.06180 --mode citations --query "prefix sharing"
$P bibtex arxiv:2309.06180 doi:10.1145/3600006.3613165
$P --help
```

Responses are cached for 7 days in `~/.cache/novelty-check/`, and requests to each source are
spaced out across processes, so parallel subagents stay within each API's rate limits.

## Development

```sh
nix develop                                    # or any Python 3.9+
python3 -m unittest discover -s tests -t .    # offline, uses recorded API answers
ruff check . && ruff format --check .
nix flake check
```

`evals/` holds a known-answer test: ideas paraphrased from published papers, which a run must
find. See `evals/README.md`. The design and the reasoning behind it are in `docs/design.md`.

## License

Apache License 2.0. Copyright 2026 David Hermann. If you redistribute this code or a modified
version, keep the copyright notice, the license and the NOTICE file, and mark the files you
changed.
