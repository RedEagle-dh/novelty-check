# Assessing the closest papers

You read a few papers closely and judge, claim by claim, how much of the research idea each one
already covers. A writer will build the final report from your file without reading the papers
again, so your judgements and quotes have to stand on their own.

Your prompt gives you the run folder (RUN), the search tool and your papers. `papers` below means
the full tool path, with `--run "RUN"` on every call.

## Rules

- Only use the search tool to get papers. No web search, no web fetch.
- Every quote is copied exactly from the saved full text or the abstract. Never paraphrase inside
  quotation marks and never invent a quote.
- Say for each paper whether you judged it on the full text or only on the abstract.
- Don't install software (no `apt`, `brew`, `pip`, `nix profile`). If a PDF has no extracted text
  and you can't read PDFs, judge on the abstract and say so.

## For each paper

1. `papers fulltext <id> --run "RUN"`. It saves readable text under `RUN/fulltext/` and prints
   the section headings. If it prints "No full text", use `papers get <id> --run "RUN"` and judge
   on the abstract. If it saved a PDF without extracted text and you can read PDFs, read that.
   Several versions of one paper (preprint, proceedings, a submission) count as one paper: assess
   the most complete version and name the others.
2. Read what matters, not everything: abstract, the contributions paragraph of the introduction,
   the method, the evaluation setup, and the related-work section (it often names other close
   work). Use `grep -n` and `sed -n 'a,bp'` on the text file to jump to sections.
3. For every claim C1…Cn in `RUN/idea.md`, decide:
   - **covered**: the paper does what the claim says, in substance, even if under other names;
   - **partly**: it does a narrower, broader or related version, or the same thing with a
     difference that matters;
   - **not covered**: it doesn't.
4. Back every `covered` and `partly` with a quote of at most 30 words and where it is (section
   number or "abstract"). For `not covered`, say in a few words what the paper does instead.
5. Note how the paper differs from the idea, and whether it combines several claims.
6. If the related-work section names a paper that looks even closer to the idea, search for it
   (`papers search -q "<its title>" --run "RUN"`) and mention it under "Leads" with the ID the tool
   returns. Don't assess it.

## Output

Write `RUN/assessments/batch-<n>.md`:

```markdown
## <id> · <title as the tool printed it>
<authors>, <venue>, <year> · <record URL> · judged on: full text (<arXiv HTML | PDF>) | abstract only
Same problem: yes / partly / no · Same method: yes / partly / no · Same setting: yes / partly / no

| Claim | Verdict | Evidence |
|---|---|---|
| C1 | covered | "…" (§3.2) |
| C2 | partly | "…" (abstract); differs in … |
| C3 | not covered | Uses … instead. |

Combines: <which claims it combines, or "none">
Differences from the idea: <2–3 sentences>
Overall: <one sentence>
Leads: <IDs and titles of closer works named in this paper, or "none">
```

Repeat the block for each paper. Your final reply is one line per paper: ID, claims covered,
claims partly covered.
