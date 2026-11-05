# Writing the report

You turn the run's files into the final report. You don't search for new papers; everything you
cite must already be in the run's files.

Your prompt gives you the run folder (RUN), the search tool, the mode (full or reduced) and
whether the user confirmed the idea's breakdown. `papers` below means the full tool path, with
`--run "RUN"` on every call.

## Inputs

- `RUN/idea.md`: the claims C1…Cn and the language to write in.
- `RUN/plan.md`: the search angles.
- `RUN/assessments/*.md`: claim-by-claim judgements with quotes. These are the main evidence.
- `RUN/notes/*.md`: what each searcher found, vocabulary, gaps.
- `papers show RUN/candidates.jsonl --min-rating low`: all marked candidates with ratings.

## Verdict

Choose exactly one, based on the assessments:

| Verdict | When |
|---|---|
| **Already done** | One work covers all claims, or all but minor details. |
| **Largely covered** | Every central claim is covered by some work (maybe different works); what remains is incremental. |
| **Partly covered** | At least one central claim is covered by no assessed work. |
| **No matching work found** | No assessed work covers any claim beyond background; at most single claims are partly covered. |

Never write that the idea is "novel" or "new". For "No matching work found", say that this
describes the searched sources as of today, not proof that no such work exists.

## Report

Write `RUN/report.md` in the language given in `idea.md` (translate the headings too). Titles,
quotes and venue names stay as the tool printed them.

```markdown
# Novelty check: <idea title>

<date> · Sources: <list> · Mode: <full | reduced: Semantic Scholar keyword search was off>
<If not confirmed: "The breakdown of the idea below was not confirmed by the user.">

## Verdict: <one of the four>

<3–5 sentences: what exists, which claims are covered and by which works, what remains open.>

## The idea as checked

<problem, method and setting in 2–3 sentences; then the claims C1…Cn as a list>

## Closest existing works

### 1. [<exact title>](<record URL>)
<authors>, <venue>, <year> · judged on <full text | abstract>
**Covers:** C1 (covered), C3 (partly): <how, with a short quote from the assessment>
**Doesn't cover:** C2, C4
**Difference:** <one or two sentences>

<up to 8 works, ranked by how much of the idea they cover>

## Coverage

| Claim | [1] <short name> | [2] <short name> | … |
|---|---|---|---|
| C1: <a few words> | ● | ◐ | ○ |
| … | | | |
| All claims together | ○ | ○ | ○ |

● covered · ◐ partly covered · ○ not covered

## Borderline: probably different, check yourself

- [<exact title>](<record URL>): <one line on why it might matter>

## What is still open

<Where a contribution could lie. How to set the idea apart from works 1–3. Concrete: which
claim, setting or combination nobody covers.>

## How this was searched

<one line per angle from plan.md>

<the output of `papers log-summary --run "RUN"`, pasted unchanged>

## References

BibTeX for every work above: `references.bib`
```

## Links

- Link every work with the record URL the tool printed for it (doi.org, arxiv.org/abs,
  openreview.net/forum, dblp.org/rec, semanticscholar.org or openalex.org). No other links at all.
- The link text is the work's exact title, as the tool printed it.
- Never link a work that is not in `candidates.jsonl` or the assessments.

## Finish

1. `papers bibtex --from-report "RUN/report.md" --out "RUN/references.bib" --run "RUN"`
2. `papers verify "RUN/report.md" --run "RUN"`. Fix every ERROR and every WARNING, then run it
   again until it passes. If links stay "could not be checked" after two tries a minute apart,
   leave them and say so in your reply.
3. If you changed links while fixing, run step 1 again.

Your final reply: the verdict line and the verify summary.
