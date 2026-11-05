# Novelty check skill: design

Date: 2026-11-05 · Status: approved by David on 2026-11-05 and implemented (see "Implementation notes" at the end)

Decisions marked **(David)** were made by David in conversation. Decisions marked **(my call)** are
proposals he can still change.

## Intent

Before starting a research project, a CS researcher needs to know whether someone has already done
it, and if so, how much of it. Missing existing work is costly: wasted months, a rejected paper, an
awkward question from a supervisor. Searching by hand across several databases is slow and easy to
get wrong, because the same idea is often published under different terms.

The skill takes a research idea, searches scholarly databases in parallel, follows citations from the
closest hits, reads the closest papers and reports:

1. whether the idea has already been done,
2. which existing works come closest, and what each one does and doesn't cover,
3. what is still open, i.e. where the user's own contribution could be.

## Users

- David and his university colleagues, all working in computer science **(David)**.
- Agents **(David)**:
  - Claude Code and Codex.
  - DeepSeek running inside agents such as Hermes Agent, Command Code and OpenCode.
  - All five are install targets of `npx skills add`; this was checked in the skills CLI's agent list
    on 2026-11-05.
- Operating systems **(David)**: Linux, mostly NixOS, and macOS. No Windows.
- Shared through the public repo `github.com/RedEagle-dh/novelty-check`, installed with
  `npx skills add RedEagle-dh/novelty-check` and updated with `npx skills update`.
  - David's personal account **(David)**.
  - Repo name **(my call)**.

## Goals

- Find existing papers, conference proceedings, preprints and technical reports that overlap with
  the idea, including ones that use different terms.
- Judge overlap part by part, not as all-or-nothing.
- Give a clear verdict with the evidence behind it, and a search log that shows how thorough the
  search was.
- Use parallel subagents where the agent supports them, and run the same steps one after another
  where it doesn't **(David)**.
- Produce BibTeX for every cited work.

## Non-goals

- General literature reviews or topic reports (the existing `deep-research` skill covers those).
- Writing a related-work section.
- Fields outside CS **(David)**, patents, and paywalled full text (no university proxy or login).
- Judging whether the idea is good or feasible.
- Tracking new papers over time. Running the skill again later covers that.

## Anti-goals (failures even if everything technically runs)

- Reporting "no matching work found" when the idea is published in one of the searched databases.
  The skill errs toward showing too much: a borderline match marked "probably different, check it"
  beats leaving it out **(my call)**.
- Citing a work that doesn't exist or has wrong metadata.
- Using a web page, blog, news article or Wikipedia as evidence. Only scholarly records count
  **(David)**.
- Sending the idea text itself to a paper database. Only short keyword queries leave the machine
  **(my call)**.
- One colleague's run using up the free API budget everyone on the campus network shares (see API
  keys).

## Constraints

- **Sources (David: CS only; the source list is my call):**
  - Semantic Scholar: abstracts, citations in both directions, recommendations.
  - DBLP: CS conference and journal coverage.
  - arXiv: preprints; in CS this is also where most industry-lab technical reports appear.
  - OpenAlex: a broad second check for workshops, journals and reports.
  - OpenReview: ICLR, NeurIPS and TMLR submissions, including ones under review or rejected; used
    when the idea is in ML.
- **No web search or general page fetching** for finding or citing papers. Allowed network targets:
  the five APIs, `doi.org` (BibTeX and metadata) and full-text URLs of papers that were already found
  through those APIs (arXiv HTML or PDF, open-access PDF links from the metadata).
- **Every cited work must resolve** to a DOI, arXiv ID, DBLP key, Semantic Scholar ID or OpenReview
  ID through the script.
- **Runs in any agent with a shell.** The search tool is a Python script that uses only the standard
  library and Python 3.9 or later, so colleagues need no `pip`, `uv` or virtualenv **(my call)**.
  - Python 3.9 is what macOS ships with the Xcode Command Line Tools.
  - On NixOS, `python3` is often not on the PATH. So `SKILL.md` never relies on the shebang. It
    calls `python3 <script>`, and if that isn't found and `nix` is available, it falls back to
    `nix run nixpkgs#python3 -- <script>`. The same goes for `pdftotext` (`nixpkgs#poppler_utils`).
  - The repo gets a `flake.nix` with a dev shell for working on and testing the script, but users
    never need it **(my call)**.
- **Licensing:**
  - The repo is Apache-2.0, copyright David Hermann **(David chose the licence; the copyright line
    is my call)**. `NOTICE` names David as the author. Under Apache-2.0, anyone who redistributes the
    code or a modified version must keep the copyright notice, the licence and the NOTICE file, and
    must mark the files they changed.
  - The coordinator, researcher and writer structure is borrowed from `deep-research`, but the text
    is our own. That skill ships without a license that would allow republishing it.
  - Code may be adapted from DeepMind's `science-skills` OpenAlex CLI (Apache-2.0) with attribution
    in `NOTICE`.
- **Facts checked against the live APIs on 2026-11-05:**
  - DBLP's search API (`dblp.org/search/publ/api`) and its `.bib` export, including the
    `dblp.uni-trier.de` mirror, sit behind a bot challenge and return HTML to scripts. The SPARQL
    endpoint `https://sparql.dblp.org/sparql` works without a challenge, and its QLever text search
    (`ql:contains-entity` / `ql:contains-word`) returns title matches. **Use SPARQL for DBLP.**
  - Semantic Scholar's keyword search returned 429 on the first keyless request, so a key is
    effectively required for search. The recommendations endpoint worked without a key.
  - OpenAlex without a key shares a $0.10/day budget per IP address (about 100 keyword searches per
    day for the whole network). A free key gives $1/day. OpenAlex's own response notice says a key
    can be requested with `POST https://api.openalex.org/api-keys` and `{"email": ...}`; the user
    then clicks a link in the email.
  - The arXiv API (`https://export.arxiv.org/api/query`, Atom XML) and the OpenReview API v2
    (`https://api2.openreview.net/notes/search`) work without a key.
  - `doi.org` content negotiation (`Accept: application/x-bibtex`) returns BibTeX, including for
    arXiv papers through their DataCite DOI `10.48550/arXiv.<id>`.

## Approaches considered

| | Approach | Trade-off |
|---|---|---|
| **A (picked)** | One repo with its own search script for all five sources plus the skill instructions | Install in one step, works in every agent, consistent records, so duplicate removal and the coverage table are reliable. We maintain a few hundred lines of Python against five APIs. |
| B | Instructions only, reusing DeepMind's OpenAlex and arXiv skills and AI2's Semantic Scholar tool | Less code, but three installs plus a separate CLI, different output formats left for the model to merge, no DBLP or OpenReview, and no way to fix them when they break. |
| C | A search server (MCP) plus a short skill | Clean tools, but each colleague has to set up the server separately in each agent, and `npx skills add` can't install it. |

David picked **A**: it is the only approach that gives colleagues on different agents a one-step
install, and consistent records matter for the coverage table.

## How it works

### Repo layout (my call)

```
<repo>/
  README.md                 # what it does, install, keys, privacy note, supported agents
  LICENSE, NOTICE
  skills/novelty-check/
    SKILL.md                # coordinator workflow
    references/
      searcher.md           # instructions for search subagents
      assessor.md           # instructions for close-reading subagents
      writer.md             # report format and rules
    scripts/
      papers.py             # the search tool (may be split into a small package)
  tests/                    # script tests with recorded API responses
  evals/                    # known-answer ideas (see Verification)
```

Skill name `novelty-check` is my call. Its description should trigger on phrases like "has this been
done", "is my idea novel", "prior work for my idea", "related work check", and the German
equivalents "Stand der Forschung", "gibt es dazu schon Arbeiten", "ist meine Idee neu", because
colleagues may write in German.

### The search script `papers.py`

One record format for every source:

```
id            canonical: DOI > arXiv ID (without version) > Semantic Scholar ID > OpenReview ID > DBLP key
ids           {doi, arxiv, s2, dblp, openalex, openreview}
title, authors, year
venue, venue_type   conference | journal | workshop | preprint | report | thesis | other
abstract            may be null
citation_count
url                 landing page of the scholarly record (doi.org, arxiv.org/abs, openreview.net/forum, dblp.org/rec)
fulltext_url        arXiv HTML/PDF or open-access PDF, if known
found_in            which databases returned it
```

Commands (exact flags are left to the builder):

- `doctor`: checks the Python version, whether keys are present and whether each API answers, and
  prints what is missing and how to fix it.
- `setup`: stores keys. It can request an OpenAlex key by email after the user has agreed and
  given an address, and it points to the Semantic Scholar key form.
- `search --source <s2|openalex|arxiv|dblp|openreview|all> --query "…" [--year-from Y] [--limit N]`:
  prints records as JSON Lines and appends each query to the run's search log (source, query, time,
  hit count, errors).
- `get <id>`: full record. Fills in missing abstracts (DBLP has none) from Semantic Scholar, then
  OpenAlex (rebuilt from its inverted abstract index), then arXiv.
- `expand <id> --mode <citations|references|recommend>`: uses Semantic Scholar, with OpenAlex
  `cited_by` / `referenced_works` as fallback.
- `fulltext <id>`: saves readable full text when available (arXiv HTML first, then an open-access
  PDF). How PDF text gets extracted is left to the builder: `pdftotext` if installed, or handing the
  PDF path to the agent if it can read PDFs.
- `merge <files…>`: removes duplicates. A match is the same DOI, the same arXiv ID, or the same
  normalised title with years at most one apart (a preprint and its later proceedings version are
  the same work: keep both venues and show the published one).
- `bibtex <id…>`: BibTeX through `doi.org` content negotiation. Without a DOI, it is generated from
  the record's metadata and marked as generated.
- `verify <report.md>`: checks that every work cited in the report resolves, and that every link in
  the report points to an allowed scholarly host. Lists failures.

API keys **(my call)**:

- Read from `S2_API_KEY` and `OPENALEX_API_KEY` environment variables, otherwise from
  `~/.config/novelty-check/keys.json` (file mode 600).
- Keys are never printed, logged or written into run folders.
- If a key is missing, `doctor` explains how to get it. The run may continue in a reduced mode only
  after the user agrees, and the report states which sources were limited. The Semantic Scholar key
  form may take days to be approved, so this case is real.
- **One key set per person, never a shared group key.** Semantic Scholar limits requests per key, and
  the throttle below only coordinates processes on one machine, so two colleagues on a shared key
  would hit each other's limit.
- **Reduced mode is a normal first experience, not an edge case.** New colleagues will often start
  before their Semantic Scholar key is approved. Reduced mode means OpenAlex, arXiv, DBLP and
  OpenReview searches, plus Semantic Scholar recommendations, which work without a key. It gets built
  and tested as properly as the full mode **(my call)**.

Sandboxed agents **(my call)**:

- Codex's default sandbox blocks network access and writes outside the project folder. `doctor`
  detects missing network access and tells the user how to allow it for this agent. The README
  documents the Codex setting.
- If `~/.cache/novelty-check/` isn't writable, the cache and lock files fall back to
  `./.novelty-check-cache/` in the working directory. Keys are only read from `~/.config`, which the
  sandbox allows. `setup` writes keys there, and if the sandbox blocks that, it tells the user the
  one command to run themselves.

Rate limits and caching **(my call)**:

- Parallel subagents each call the script, so throttling has to work across processes: a lock file
  plus a "last request" timestamp per source in `~/.cache/novelty-check/`.
- Target intervals:
  - Semantic Scholar: 1 request/s with a key.
  - arXiv: one request every 3 s, as its API terms ask.
  - OpenAlex: at most 10/s.
  - DBLP SPARQL and OpenReview: about 1/s.
- On 429 or 5xx, retry with backoff (respect `Retry-After`) at most 3 times. After that, record the
  failure in the search log. A failed query is never silently dropped.
- Responses are cached on disk for 7 days, keyed by request without the key. Reruns are cheap and
  overlapping queries from parallel searchers cost nothing extra.
- Set a descriptive generic `User-Agent`. Don't put personal email addresses in requests.

### Workflow in `SKILL.md`

The agent acts as coordinator. Every step writes files into the run folder, so the parallel and the
step-by-step modes produce the same output.

0. **Check.** Run `papers.py doctor`. If keys are missing, offer `setup`. Continue in reduced mode
   only with the user's agreement.
1. **Intake.** Take the idea from the chat or from a file (Markdown, text, or PDF if the agent can
   read it). Write `idea.md` with:
   - the research question or problem,
   - the approach or method,
   - the setting (domain, data, system, users),
   - the claimed contributions as numbered claims C1…Cn, which are the units the coverage is judged
     on,
   - key terms with synonyms and older or alternative names (CS terms drift: "LLM agents",
     "autonomous agents", "multi-agent systems"),
   - optionally, papers the user already knows about, used as extra starting points.

   Show `idea.md` to the user and ask them to confirm or correct it. Apart from setup, this is the
   only stop that waits for the user.
2. **Plan.** Choose 3–5 search angles. Each angle is one part of the idea or a combination of
   parts. One angle is always "different vocabulary and older work". Each angle gets 4–8 short
   keyword queries and a list of sources. Write `plan.md`. OpenReview is included only when the idea
   is in ML.
3. **Search.** One searcher per angle, in parallel when the agent can start subagents. Otherwise the
   coordinator works through the angles itself, in order, following the same `searcher.md`.
   - Subagent tools: Claude Code has the Agent tool, Codex has `spawn_agent`.
   - For OpenCode, Hermes Agent and Command Code, the builder confirms which subagent tool exists.
   - `SKILL.md` names the known tools and tells any agent without one to use step-by-step mode.

   A searcher:
   - runs its queries,
   - fetches abstracts for hits that have none,
   - screens every hit by title and abstract against C1…Cn,
   - rates each candidate high, medium or low, noting which claims it touches,
   - writes `notes/<angle>.md` and `candidates/<angle>.jsonl`.

   Budget: about 25 script calls per searcher.
4. **Expand.** Merge all candidates, then pick up to 8 "seed" papers rated highest. Run `expand` on
   each in all three modes, and have one searcher screen the new hits the same way. **One round
   only.**
5. **Assess.** Take the up to 12 closest papers and give them to assessors in batches of 3–4 (in
   parallel when possible). For each paper, the assessor:
   - reads the abstract, plus the full text when available, preferring arXiv HTML,
   - marks each claim covered, partly covered or not covered,
   - backs each mark with a short quote from the paper, and the section when it comes from full
     text,
   - states what the paper does differently,
   - states whether the judgement was made on the abstract or the full text.

   Writes `assessments/<batch>.md`.
6. **Write.** A writer subagent (or the coordinator) writes `report.md` and builds `references.bib`
   with `papers.py bibtex`.
7. **Verify.** Run `papers.py verify report.md`. Fix or remove anything that doesn't resolve or that
   links to a non-scholarly host, then run it again until it passes.
8. **Deliver.** In chat: the verdict, the three closest works and the path to the report.

Target per run: about 20–30 minutes and at most about 150 API calls. That is roughly $0.05 of
OpenAlex budget, so a free key covers well over 10 runs a day. These are targets, not hard limits.

### Run folder (my call)

`./novelty-checks/<YYYY-MM-DD>-<short-slug>/` relative to where the agent runs. An existing folder is
never overwritten: the new run gets a `-2`, `-3`, … suffix. Contents: `idea.md`, `plan.md`, `notes/`,
`candidates/`, `assessments/`, `search-log.jsonl`, `report.md`, `references.bib`.

### Report format (my call)

Written in the language the user described the idea in (German or English). Paper titles, quotes and
BibTeX stay in the original language.

1. Header: idea title, date, sources searched, which sources ran in reduced mode.
2. **Verdict**, one of:
   - Already done
   - Largely covered
   - Partly covered
   - No matching work found

   Follow it with 3–5 sentences of justification. Never say "novel"; the strongest wording is "no
   matching work found in <sources> as of <date>".
3. **Closest works**, ranked. For each:
   - the citation, venue and year, and a link to the record,
   - which claims it covers and which it doesn't, and how it differs,
   - whether it was judged on the abstract or the full text.
4. **Coverage table**: claims C1…Cn as rows, the closest works as columns, cells marked covered,
   partly covered or not covered. A last row asks whether any single work covers the full
   combination.
5. **Borderline, probably different, check yourself.** A short list.
6. **What's open**: where a contribution could lie and how to set the idea apart from the closest
   works.
7. **Search log**: for each angle, the queries, sources, dates, hit counts and failures; plus the
   seed papers used for citation following.
8. References: points to `references.bib`.

### Privacy

- Only short keyword queries and paper IDs go to the databases. The idea text stays in the run
  folder.
- The README notes that the agent's own model provider (Anthropic, OpenAI, DeepSeek, …) sees the
  idea, which the skill can't control.

## Verification

- **Script tests** with recorded API responses for parsing, duplicate removal, merging and BibTeX
  handling, plus `doctor` as a live check against each API.
- **Known-answer eval** **(my call)**:
  - About six ideas in `evals/`. Four are paraphrases of real CS papers published 2023–2026, one
    each from ML, systems, HCI and security. They are written the way a student would describe the
    idea, deliberately avoiding the paper's own key terms.
  - Pass: the original paper appears among the five closest works, and the verdict is "Already
    done" or "Largely covered".
  - One or two ideas are deliberately new combinations. For these, check by hand that the skill
    doesn't claim "Already done" without real evidence.
- Test matrix:
  - Claude Code and Codex, both in parallel mode.
  - OpenCode with DeepSeek, in whichever mode it supports.
  - Step-by-step mode forced once in Claude Code, so both modes get compared on the same eval.
  - Linux (NixOS and a non-Nix distribution) and macOS. CI runs the script tests on both.
- Keys for development:
  - David requests a Semantic Scholar key now. Approval may take days.
  - An OpenAlex key is requested through the email flow.
  - Until the Semantic Scholar key arrives, the reduced mode is built and tested first. Recorded
    full-mode responses and the full-mode eval follow once it does.

## Left to the builder

- Exact query syntax, field selection and paging for each API, and which arXiv categories to
  include (default `cs.*` plus `stat.ML` and `eess.*`).
- Whether `papers.py` is one file or a small package.
- How PDF text gets extracted.
- Fine-tuning the caps above.
- README wording.
- How each agent finds the skill's own directory so it can call `scripts/papers.py`, and checking
  that `npx skills add` installs into Claude Code, Codex and the other agents colleagues use.

## Open questions for David

None. The reviewer's questions are answered above.

## Implementation notes (2026-11-05)

Where the build differs from or adds to the design above:

- **OpenReview** answers keyword searches without an account, but fetching a single note by ID
  now returns a bot challenge. Records are therefore kept from search results in the run's
  record store (`records.jsonl`), and `verify` checks OpenReview links against that store.
  Copies of papers that OpenReview imports from DBLP, ORCID or author uploads are dropped,
  because the other sources already cover them.
- **Extra commands** beyond the design's list:
  - `init-run`: creates the run folder.
  - `mark`, `merge`, `show`: searchers record candidates through the tool instead of writing JSON
    by hand.
  - `log-summary`: the report's search log as Markdown tables.
- **`expand --query`** keeps only citing works that match keywords (through OpenAlex). Without it,
  the citations of a paper cited thousands of times are mostly noise.
- **`scripts/papers`** is a `sh` wrapper that finds `python3`, or falls back to
  `nix run nixpkgs#python3`.
- **First known-answer eval** (`systems-serving-memory`, Claude Code, parallel, reduced mode):
  - Passed: the expected paper was ranked 1st, with the verdict "Already done".
  - About 25 minutes and about 1.3M subagent tokens.
  - 88 keyword queries and 29 citation lookups.
  - `verify`: 22 links, 0 errors.
- **Changes from what that eval showed:**
  - SKILL.md now gives an explicit prompt template for the citation-following searcher.
  - Several versions of one paper are assessed once.
  - Assessors must not install software (one had installed `poppler-utils` on its own).
  - The OpenAlex cap per angle is spelled out.
  - `log-summary` prints one row per query instead of one per source call.
- **Codex smoke test:**
  - The default `workspace-write` sandbox has no network. `doctor` reports BLOCKED, and the cache
    falls back to the working directory.
  - With `sandbox_workspace_write.network_access=true`, every source works.
  - A full run in Codex and in OpenCode is still to do.

