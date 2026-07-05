# Phase 0 results: rtk rewrite coverage on real command history

Date: 2026-07-05. Binary: rtk v0.43.0 (rtk-x86_64-unknown-linux-musl,
sha256 ff8a1e77... matches published checksums.txt), pinned in bin/, run with
isolated HOME (bench/rtk-eval/home/), never on PATH, never `rtk init`.

Input: all 130,196 bash toolCall/toolResult pairs from all sessions
(all-commands.jsonl via phase0.py dump; 117,871 unique command strings).

## Coverage — GATE PASSED (threshold was 15% of output mass)

  calls rewritten:      44,828 / 130,196  (34.4%)
  output mass covered:  71.9M / 200.1M chars  (35.9%)

Top targets by output mass (full numbers in phase0-results.json):
  rg          21.8M chars (3,461 calls)     git-diff   4.9M (1,056)
  grep        11.4M (11,318)                curl       4.8M (3,548)
  read/cat    10.8M (5,548)                 npx        4.6M (2,698)
  ls           3.9M (5,290)                 git-status 1.5M (1,211)

Coverage sits exactly where our token mass lives (search + file reads + git),
i.e. the layer the deleted post-hoc filters never touched.

## Phase 0b: pipe-consumer quantification + purity (phase0b.py, rewrites.jsonl)

Of the 44,828 rewritten calls:
  no-pipe        19,017 calls (42.4%)   21.2M chars (29.4%)
  display pipe    9,359 calls (20.9%)   12.8M chars (17.8%)  (head/tail/cat)
  computation    16,452 calls (36.7%)   37.9M chars (52.8%)  (grep 2943, python3 915, jq 773, wc 413, sed, awk, ...)

Over HALF the covered output mass flows into downstream programs whose
correctness depends on rtk's output format. This is the central Phase 1
question, not a side case. (Classifier is segment-based and approximate —
heredoc content occasionally parses as consumers ("def", "function") —
but the order of magnitude is unambiguous.)

Purity: unshare -rn is blocked for unprivileged users on this box (the
initial 500/500 "mismatches" were the harness failing, not rtk). Replaced
with strace network tracing: 60 sampled rewrites, ZERO network syscalls.
`rtk rewrite` verified as a pure local mapping. Caveat recorded: the full
117k-command run happened before this verification, and command strings can
embed secrets (heredocs); all-commands.jsonl and rewrites.jsonl are
gitignored and must stay local.

vitest passthrough (string level): `npx vitest run FILE --flags` ->
`rtk vitest FILE --flags` — file args and flags preserved, `run` subsumed.
Behavioral equivalence (exit code, failing-test rendering) remains Phase 1.

## Behavior notes (probes, not yet proof)

- Compound commands handled: `cd /repo && git status` ->
  `cd /repo && rtk git status`. The failure mode that made upstream's
  detection inert (0/908) and the third-party extension blind does not apply.
- Exit codes: 3 = rewritten (docs claim 0), 1 + empty = no equivalent.
  Integration code must test output non-empty, not exit 0.
- Pipe-consumer hazard probed and survived at micro scale: `rtk rg | wc -l`
  same count as raw; `rtk grep -c` passes count through; `rtk read x.json |
  jq` stays parseable. rtk appears pipe-aware (plain output when piped).
- `rtk rewrite` wrote no files to its isolated HOME (pure string mapping).

## Carry-forward requirements for Phase 1 fixtures

1. Pipe-consumer cases at realistic scale: `rg -l | xargs`, `| wc -l`,
   `| jq` on large outputs — silent wrong numbers are the worst class.
2. `rtk curl`: 4.8M chars of real curl traffic would be rewritten; fixtures
   must verify API/JSON responses arrive unaltered (agent flows parse them).
3. `npx` family: `npx vitest run` -> `rtk vitest` (runner swap, not prefix) —
   planted failing tests must survive rtk vitest's rendering, and its exit
   code must still signal failure.
4. `git add`/`commit` family is rewritten too (817K chars) — verify mutating
   commands still perform the mutation identically and only the report is
   compacted.

## Reproduce

  python3 phase0.py all     # ~3 min dump + ~2 min rewrite (8 threads)
  # outputs: all-commands.jsonl, phase0-results.json, phase0-sample-rewrites.txt
