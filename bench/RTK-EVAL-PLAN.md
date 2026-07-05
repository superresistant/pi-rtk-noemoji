# rtk evaluation plan (pre-execution command rewriting, rtk-ai/rtk binary)

Question: does rewriting bash commands to `rtk` equivalents before execution
earn a place in our pi setup — measured on our real usage, with the same
discipline that killed the post-hoc filters (bench/RESULTS.md)?

Ordering principle: cheap offline gates first; no gpt-5.5 spend and no model
contact with rtk output until the do-no-harm gates pass. Probe harness can be
built in parallel at any time (none of it depends on rtk passing).

Cross-cutting safety: pinned rtk release binary, checksum verified; never
`rtk init` (no hooks, no global integration); binary lives inside fixture
dirs, never on default PATH; global pi config untouched — all arm wiring is
project-local. Artifacts under bench/rtk-eval/. Fixed seeds, everything
logged.

## Phase 0 — coverage replay. Offline, zero risk. GATE

`rtk rewrite` is a dry string mapping. Feed it all ~130k real bash commands
from the corpus (rebuild with bench/extract.py if needed).

Measure:
- fraction of commands rewritten, and weighted by historical output chars
  (the number that matters — coverage of token mass, not of call count)
- per-category breakdown (git, tests, search, reads, ls, docker, ...)
- compound-command handling: `cd /repo && git status` is our dominant shape;
  upstream-style first-segment detection dies here (the 0/908 lesson)

Gate: rewritten commands must cover a meaningful share of real bash output
mass (guideline >= 15% of chars). Below: stop, write findings, done.

## Phase 1 — seeded-fact fixtures. Offline. DO-NO-HARM GATE

Fixtures reproducing the output shapes from the corpus, with facts we planted
and therefore know exactly:
- vitest suite, exactly 2 failing tests with known names — run as
  `rtk vitest` (the rewrite swaps the runner); exit code must still be
  nonzero and both test names must render
- git repo: 1 staged, 1 modified, 1 untracked, 1 UU conflict, known branch
- diff touching 3 known files with known +/- counts
- rg search with matches at known file:line
- build with one known error line buried in noise
- PIPE-CONSUMER FIDELITY (elevated to primary by Phase 0b: 52.8% of covered
  output mass feeds computation consumers): `rtk rg | wc -l`, `rtk rg -l |
  xargs`, `rtk read x.json | jq`, `rtk git status --porcelain | wc -l`,
  `rtk grep -c` — downstream results must be byte-identical to raw
- `rtk curl` returning JSON: response body must reach the consumer unaltered
- mutating family: `rtk git add`/`commit` in a scratch repo — resulting git
  state must be identical to raw; only the report may differ

Run each command raw and via rtk, same moment, same state. Oracle is a
checklist: every planted fact present or derivable in rtk output. ttok both
sides for savings per category.

Gate: 100% recall on failure signals (failing test names, conflict, error
line). Any loss: stop. This is the class of bug that made us delete the
filters — 174 vitest runs reported as passing.

## Phase 2 — live behavioral A/B probe. Real pi sessions. GATE

The offline phases prove information survives; this phase asks whether the
model uses it well. Separate failure surface: format distrust (re-running the
raw command, erasing savings), misreading aggregates, rtk vocabulary leaking
into model-authored files, wasted turns commenting on odd output.

Mechanics (subagent skill): one tmux session per trial,
`pi --model openai-codex/gpt-5.5 -p @P.md`, stdout/stderr redirected,
`EXIT_CODE=$?` appended, completion = session gone + exit code. Up to 9
parallel. Verify model availability first (`pi --list-models`).

Deviation from the skill, deliberate: trials are experimental subjects, not
workers. Task file contains only the natural task ("tests are failing in this
repo, fix them"). No OUTPUT RULES suffix, no status-file contract, nothing
hinting at an experiment.

Per trial: fresh fixture copy at /tmp/rtk-probe/<task>-<arm>-<n>/,
git-initialized, planted ground truth. Arm isolation is project-local: rtk
arm's fixture carries `.pi/extensions/rtk-probe/` — our own ~30-line
extension shelling out to the pinned binary stored inside the fixture (not
the 7,868-line third-party extension; keep the variable isolated to the
binary). Control arm: identical fixture, no extension dir. Same spawn line
both arms; sessions land in ~/.pi/agent/sessions/ where our mining tooling
already works.

Design (tightened after critical review): paired trials — each control/rtk
pair runs on byte-identical fresh fixture copies; report per-pair deltas and
medians, not means. Pre-registered thresholds, written before the first
spawn: (a) task success rate in the rtk arm >= control arm - 5 points
aggregated across tasks; (b) median end-to-end tokens per completed task
reduced by >= 15%; (c) redundant raw re-query (same command re-run without
rtk within 3 turns of a rewritten call) in < 10% of trials; (d) zero
incorrect final answers traceable to a compacted output. Fail any -> stop.
Budget estimate: 4 tasks x 8 trials x 2 arms = 64 gpt-5.5 sessions, each a
few turns on small fixtures; plus <= 16 spark sessions. Both models verified
available via `pi --list-models` (2026-07-05).

Arms:
- openai-codex/gpt-5.5 (main model): 8 paired trials per task. Gating.
- gpt-5.3-codex-spark: small n, exploratory, never gating. Expected to fail
  tool use in normal conditions — that expectation is the control. Equal
  failure in both arms = rtk irrelevant for weak models; divergence either
  way is informative (less noise to misread vs unfamiliar format as the
  final straw).

Tasks (objectively checkable): fix the failing test; report exact uncommitted
state; locate a definition via search; summarize what a large diff changes.

Metrics, all post-hoc from session JSONLs + checker scripts (never the
model's own claim of success):
- task success: checker reruns the suite / diffs answer vs planted state
- end-to-end tokens to completion (the only savings number that matters)
- turn count, tool-call sequence
- redundant re-query: same command re-run raw within N turns of a rewritten
  one — the signature of format distrust
- rtk leakage into model-authored scripts, commits, prose
- confusion markers in assistant text

Gate (gpt-5.5 arm): task success not degraded AND end-to-end tokens down AND
redundant re-queries ~0. A model that keeps double-checking raw output kills
the premise regardless of compression quality.

## Phase 3 — re-execution A/B on real repos. Offline. Parallel with Phase 2

Sample real read-only commands from the corpus (strict whitelist: git
status/diff/log, ls, cat, rg, find — nothing mutating), re-execute in their
original cwd cloned to /tmp, network off, timeouts. Repo drift is irrelevant:
pairing is raw-vs-rtk at the same moment; history only supplies realistic
command and repo distribution. Ground truth from machine-readable forms we
run ourselves (git status --porcelain). Per call: rewritten or pass-through,
tokens both sides, facts preserved, latency delta. Plus 30 random
before/after pairs for eyeball review.

## Phase 4 — downstream-usage validation. Optional, sharpest oracle

Sessions record what the agent did with each output: file edited next, line
quoted, test name fixed. Extract consumed artifacts from history, reproduce
the scenario in fixtures, check the consumed artifact survives rtk rendering.
Answers the only question that matters: would the agent still have been able
to take its next action?

## Phase 5 — shadow period. Confirmation, never discovery

Only if all gates pass: enable for real work for a bounded period, pi-stats
watching end-to-end token totals per project. Live sessions are noisy and
unrepeatable; they confirm, they do not decide.

## Decision summary

0. coverage of real command mix        -> else stop
1. planted failure-signal recall 100%  -> else stop
2. gpt-5.5: success held, tokens down, no distrust loop -> else stop
3. fact preservation + net tokens on real repos (evidence, parallel)
4. consumed-artifact recall (optional sharpening)
5. shadow period (confirmation)
