---
name: novelty-check
description: Checks whether a computer-science research idea has already been done. Searches only scholarly sources (Semantic Scholar, DBLP, arXiv, OpenAlex, OpenReview), follows citations, reads the closest papers and reports which parts of the idea existing work covers, which works come closest, and what is still open, with a search log and BibTeX. Use when someone asks "has this been done?", "is my idea novel?", "is there prior work on…", wants a novelty or related-work check before a thesis, paper or project, or asks in German ("Gibt es dazu schon Arbeiten?", "Ist meine Idee neu?", "Stand der Forschung zu meiner Idee"). Not for general literature reviews or fields outside computer science.
license: Apache-2.0
metadata:
  author: David Hermann
  version: "0.1.0"
---

# Novelty check

You coordinate a search for existing work that overlaps with the user's research idea, then
report how much of the idea is already covered. A run takes about 20–30 minutes; tell the user
that when you start.

## Rules for you and every subagent

1. **Scholarly records only.** Find, read and cite works only through the search tool below. Do
   not use web search or general web fetching for this task, not even to "double-check". A blog
   post, news article, product page or Wikipedia entry is never evidence.
2. **Nothing from memory.** If you remember a relevant paper, search for its title with the tool.
   It counts only if the tool returns it. Never type a title, author, year, DOI, quote or BibTeX
   entry yourself; take them from tool output.
3. **Keep the idea private.** Queries are short keyword strings (2–6 words). Never paste
   sentences from the idea into a query.
4. **Report too much rather than too little.** Missing an existing paper is the worst outcome.
   A borderline match goes in the report as "probably different, check it".
5. **Never call the idea "novel".** The strongest verdict is "No matching work found in the
   searched sources as of <date>".

## The search tool

The tool is `scripts/papers` in this skill's directory (SKILL_DIR). If your agent did not tell
you SKILL_DIR, find it:

```sh
for d in ./.agents/skills ./.claude/skills ~/.agents/skills ~/.claude/skills ~/.codex/skills \
         ~/.config/opencode/skills ~/.hermes/skills ~/.commandcode/skills; do
  [ -f "$d/novelty-check/scripts/papers" ] && echo "$d/novelty-check" && break
done
# still nothing: find ~ -path '*/novelty-check/scripts/papers' 2>/dev/null | head -1
```

Call it as `sh <SKILL_DIR>/scripts/papers <command> …` and write the full path every time, since
shell variables may not survive between commands. It needs Python 3.9+; the wrapper falls back to
`nix run nixpkgs#python3` on NixOS. `sh <SKILL_DIR>/scripts/papers <command> --help` explains each
command. Below, `papers` is short for that full invocation.

## Workflow

| Step | Who | Writes |
|---|---|---|
| 0. Check | you | – |
| 1. Intake | you, with the user | `idea.md` |
| 2. Plan | you | `plan.md` |
| 3. Search | one searcher per angle, in parallel | `notes/<angle>.md`, `candidates/<angle>.jsonl` |
| 4. Expand | you, plus one searcher | `candidates/citations.jsonl`, `candidates.jsonl` |
| 5. Assess | assessors, 3–4 papers each, in parallel | `assessments/batch-<n>.md` |
| 6. Write | one writer | `report.md`, `references.bib` |
| 7. Verify | the writer, then you check | – |
| 8. Deliver | you | – |

All files live in the run folder (RUN) that step 1 creates. Steps hand over through these files,
so the result is the same whether subagents run in parallel or you do every step yourself.

### 0. Check

Run `papers doctor`. It prints a mode:

- **FULL**: go on.
- **REDUCED** (no Semantic Scholar key, the key was rejected, or Semantic Scholar is unreachable):
  Semantic Scholar keyword search is unavailable; the other sources still work. Show the user the "To fix" lines from the doctor output and
  ask whether to continue in reduced mode or set the key up first.
- **BLOCKED** (no network): stop and show the user the fix from the doctor output.

Never ask the user to paste an API key into the chat. They run `papers setup` in their own
terminal, or set `S2_API_KEY` / `OPENALEX_API_KEY`.

### 1. Intake

1. Get the idea from the chat or from a file the user names (Markdown, text, or a PDF if you can
   read PDFs).
2. Create the run folder: `papers init-run --title "<3–6 word title>"`. It prints RUN's absolute
   path. Run it in the user's project directory unless they want the results elsewhere
   (`--base <dir>`).
3. Write `RUN/idea.md` in this shape, in the language the user wrote in:

```markdown
# <idea title>
Language: <English | German | …>

## Problem / research question
## Approach / method
## Setting
<domain, data, system, users, constraints>

## Claims
- C1: <one sentence a paper could match, e.g. "Stores the KV cache in fixed-size blocks that need not be contiguous">
- C2: …
<3–6 claims. Together they make up the contribution; the combination is often the new part.>

## Key terms
| Term in the idea | Synonyms, older or neighbouring terms |
|---|---|

## Related work the user already knows
<titles or IDs the user mentioned; "none" otherwise>
```

4. Show the user the claims and key terms and ask them to correct or confirm, in one message.
   This and step 0 are the only places you wait for the user. If you can't ask (a
   non-interactive run), continue and note in the report that the breakdown was not confirmed.

### 2. Plan

Write `RUN/plan.md` with 3–5 search angles. Each angle is one part of the idea or a combination
of parts, and gets:

- a short name (`problem`, `method`, `method-in-setting`, …),
- the claims it focuses on,
- 4–8 starting queries of 2–6 words, mixing the idea's own terms with synonyms,
- its sources: `default` (Semantic Scholar, OpenAlex, arXiv, DBLP), plus `openreview` when the
  idea is in machine learning,
- a year range only if the user asked for one.

Always include an angle named `vocabulary` that searches with different and older terms: how
would someone from a neighbouring field, or from ten years ago, have named this? If the user
listed related work, add those titles as queries to the closest angle.

### 3. Search

Start one searcher per angle (see "Subagents" below), all at once, with this prompt. Fill in
everything in braces:

```text
You are a search subagent in a novelty check of a computer-science research idea.
First read {SKILL_DIR}/references/searcher.md and follow it exactly. Then read {RUN}/idea.md.

Search tool: sh {SKILL_DIR}/scripts/papers   (always add: --run "{RUN}" --angle {angle})
Your angle: {angle}, focusing on {claims}: {one sentence on what to look for}
Sources: {default | default,openreview}
Starting queries:
- {query}
- …
Write your notes to {RUN}/notes/{angle}.md and record candidates with
`mark … --to {RUN}/candidates/{angle}.jsonl`.
When done, reply in at most 5 lines: candidates per rating and the 3 closest works (ID, title).
```

Wait until all searchers are done.

### 4. Expand

1. `papers merge RUN/candidates/*.jsonl --out RUN/candidates.jsonl --run RUN`
2. Pick up to 8 seeds: every `high`, then the `medium` ones touching the most claims.
3. Start one searcher for the seeds:

```text
You are a search subagent in a novelty check of a computer-science research idea.
First read {SKILL_DIR}/references/searcher.md and follow it exactly. Then read {RUN}/idea.md.

Search tool: sh {SKILL_DIR}/scripts/papers   (always add: --run "{RUN}" --angle citations)
Your angle: citations. Instead of keyword queries, follow citations from these seed papers,
which the other searchers found closest to the idea:
- {id}  {title}{, cited more than 300 times}
- …
For each seed run `expand <id>`. For seeds cited more than 300 times, also run
`expand <id> --mode citations --query "<2–4 key terms of the idea>"`, which keeps only citing
works that match. Look especially for work that predates or rivals the seeds. One round only:
don't expand the new hits.
Write your notes to {RUN}/notes/citations.md and record candidates with
`mark … --to {RUN}/candidates/citations.jsonl`.
When done, reply in at most 5 lines: candidates per rating and the 3 closest works (ID, title).
```

4. Merge again (same command as 1).

### 5. Assess

Take up to 12 works from `papers show RUN/candidates.jsonl --top 14`: all `high`, then `medium`
by number of claims. Several versions of one paper (preprint, proceedings, an OpenReview
submission) count once: keep the published one. Split them into batches of 3–4 and start one
assessor per batch, in parallel:

```text
You are an assessor in a novelty check of a computer-science research idea.
First read {SKILL_DIR}/references/assessor.md and follow it exactly. Then read {RUN}/idea.md.

Search tool: sh {SKILL_DIR}/scripts/papers   (always add: --run "{RUN}")
Your papers:
- {id}  {title}
- …
Write your assessment to {RUN}/assessments/batch-{n}.md.
When done, reply with one line per paper: ID, claims covered, claims partly covered.
```

### 6. Write and 7. Verify

Start one writer:

```text
You write the report of a novelty check of a computer-science research idea.
First read {SKILL_DIR}/references/writer.md and follow it exactly.

Search tool: sh {SKILL_DIR}/scripts/papers   (always add: --run "{RUN}")
Run folder: {RUN}
Mode: {full | reduced}; idea confirmed by the user: {yes | no}
Write {RUN}/report.md and {RUN}/references.bib, and run `verify` until it passes.
When done, reply with the verdict line and the verify summary.
```

Then run `papers verify RUN/report.md --run RUN` yourself. If it reports errors, fix them (remove
the claim or replace the link with one the tool returned) and run it again.

### 8. Deliver

Tell the user in a few lines, in their language:

- the verdict, with one sentence on why,
- the three closest works, each as a link with its title,
- the path to `report.md` (and `references.bib`),
- that sources were limited, if the run was in reduced mode,
- that this is a search of the named databases, not a proof that nothing else exists.

## Subagents

Every subagent starts without this conversation. Give it the full prompt from the templates
above, with absolute paths.

- **Claude Code:** the Agent tool (`general-purpose`, in the foreground). Put all calls of one
  step in a single message so they run in parallel.
- **Codex:** `spawn_agent` for each task, then wait for all of them.
- **OpenCode:** the Task tool with the `general` subagent.
- **Hermes Agent and others:** any tool that starts a sub-agent with its own context.

**No subagent tool?** Do every task yourself, one after another, in the same order. Before each
task, read the same reference file the subagent would read, and write the same files. After a
task, rely on what you wrote to disk rather than on earlier tool output.

## Files in a run folder

```
idea.md  plan.md  notes/  candidates/  candidates.jsonl  assessments/  fulltext/
records.jsonl      every record the tool has seen in this run
search-log.jsonl   every query, its source, time, hit count and errors
report.md  references.bib
```
