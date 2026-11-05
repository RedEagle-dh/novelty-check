# Known-answer evaluation

Unit tests check the search tool. This checks the whole skill: does a run actually find existing
work when the idea is described in other words?

`ideas/` holds research ideas written the way a student might describe them, deliberately
avoiding the published paper's own key terms. `expected.json` names the paper each idea comes
from and the verdicts that count as correct.

| Idea | Source paper |
|---|---|
| `ml-preference-tuning` | Direct Preference Optimization (NeurIPS 2023) |
| `systems-serving-memory` | PagedAttention / vLLM (SOSP 2023) |
| `security-adversarial-suffix` | Universal and Transferable Adversarial Attacks on Aligned LMs (2023) |
| `hci-simulated-town` | Generative Agents (UIST 2023) |
| `open-thermal-ci` | none known; judged by hand |

## Running one

1. In an empty directory, start your agent and ask: "Run a novelty check on this idea:" followed
   by the file's text. Confirm the claims as they are.
2. When it's done, score the run folder:

   ```sh
   python3 evals/score.py systems-serving-memory novelty-checks/<date>-<title>
   ```

A run passes when an expected paper is among the first five closest works and the verdict is
accepted. For `open-thermal-ci`, read the report: an "Already done" verdict must rest on a paper
that really does all of it.

Run the set in Claude Code and Codex (parallel) and once with subagents switched off
(step-by-step) after changes to `SKILL.md`, the reference files or the search tool. These papers
are well known, so passing is the minimum bar; add harder, less-cited cases as you meet them.
