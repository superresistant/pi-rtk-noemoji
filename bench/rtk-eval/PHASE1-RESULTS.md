# Phase 1 results: seeded-fact fixtures — PASSED WITH GUARD (28/28)

Resolution 2026-07-05 (Edouard: no upstream reporting, take what works,
improve it): mitigation (b) implemented — guarded rewrite. Rule: never
rewrite a command whose rtk output would be consumed by a machine (pipe into
anything but head/tail/cat/less/more, stdout redirect to file, command
substitution). Single implementation in bench/rtk-eval/probe-ext/guard.ts,
used by both the Phase 1 harness (--guarded) and the Phase 2 probe extension.

Guarded re-run: 28/28 gates (the porcelain|wc case is correctly declined and
runs raw). Guard unit tests: 20/20 (guard-test.ts) incl. pipe chains,
redirects, substitutions, compound commands.

Guard cost on real history (guard-stats.ts over rewrites.jsonl): keeps
27,947/44,828 rewritable calls (62.3%), 33.5M chars (46.6% of coverable mass)
= net 16.7% of ALL bash output — still above the Phase 0 gate threshold.
Conservatism note: one unsafe segment declines the whole compound command
(observed live: model chained `git status && git status --short | wc -l`,
whole command ran raw, answer correct). Per-segment mixing is a possible
later refinement.

Probe extension (bench/rtk-eval/probe-ext/index.ts) smoke-tested in a real
isolated gpt-5.5 session: `git status` typed by the model executed as
`rtk git status` (PATH prefix injected execution-only), the model read rtk's
compact output and answered correctly; decision log written outside the
worktree (RTK_PROBE_LOG env — in-worktree logging polluted git status until
moved); rtk state isolated via XDG_DATA_HOME; real home verified clean.
Phase 2 is UNBLOCKED.

Original (unguarded) findings below, kept for the record.

# Original run: GATE FAILED (narrow, characterized)

Date: 2026-07-05. Harness: phase1.py (fixtures under /tmp/rtk-phase1/, rtk
v0.43.0 via private bin dir, isolated HOME, real commands executed raw vs
their actual `rtk rewrite` mapping, same moment, same state).

Score: 27/28 gates, 17/18 info checks. Per the pre-registered rule (any gate
failure stops the pipeline), Phase 2 is BLOCKED pending a mitigation decision.

## What passed (the important survivals)

- vitest (as `rtk vitest`): both planted failing test names render, failure
  count present as "FAIL (2)" (own format; raw says "2 failed" — info-level
  mismatch only), exit code still nonzero. The failure-hiding class that
  killed the old filters does NOT reproduce.
- tsc (as `rtk tsc`): error file + TS2322 survive, exit nonzero.
- Mutating git (`rtk git add && rtk git commit`): tree hash, worktree state,
  commit message byte-identical to raw.
- Pipe fidelity for rg / grep / cat-read / curl: byte-identical downstream
  results, including `| jq` and `| wc -l`.
- curl body: byte-identical (JSON untouched).
- git status/diff/log/ls as VIEWS: all planted facts render (branch, staged/
  modified/untracked/conflict files, 3 diff files with changed lines).

## The gate failure: format instability under computation consumers

`rtk git status --porcelain | wc -l` returns 6 vs raw 7 — trailing newline
stripped. Follow-up bounding:

  git status --porcelain   raw 7 lines -> rtk 6   (off-by-one newline)
  git status --short       raw 7 -> rtk 6         (same)
  git diff                 raw 48 -> rtk 46       (piped output not raw)
  ls -la                   raw 7 -> rtk 4         (compacts even when piped)
  cat/read json            identical
  rg / grep                identical (incl. trailing newline; rg -l order
                           differs — set identical, order-sensitive consumers
                           beware)

Class: rtk git-family and ls outputs are not format-stable when piped into
computation consumers; counts derived from them are silently wrong. This is
exactly the silent-wrong-number class Phase 1 exists to catch.

Blast radius in real history (rewrites.jsonl): 55 calls pipe `rtk git status`
into wc; 764 calls pipe any rtk output into wc; the full computation-consumer
class is 16,452 calls / 52.8% of covered output mass (Phase 0b) — of which
the git/ls share is the demonstrably unsafe part; rg/grep/read/curl (the bulk
of the mass) tested clean.

## Token note

Fixture outputs are deliberately tiny (facts, not savings, are the point);
savings numbers here are not representative — git-status 73%, ls 75%, but
vitest 2% (stack traces retained; full output tee'd to a log file whose path
is printed — actually a reasonable design for agents) and tsc NEGATIVE
(-46%: header overhead exceeds tiny output). Real savings must come from
Phase 3 on real repos. Observation: rtk adds overhead on small outputs —
the same "filtered longer than original" pattern we measured in the old
filters, presumably amortized on large outputs.

## Mitigation options (decision needed before Phase 2)

a) Report upstream (trailing-newline strip on porcelain output is plainly a
   bug; the piped-diff/ls behavior is arguably intended but agent-hostile).
b) Integration-side guard: our probe extension refuses the rewrite when the
   rtk-targeted segment pipes into a computation consumer. Cost: skips 36.7%
   of rewritten calls (52.8% of covered mass); keeps the clean 63%/47%.
   Conservative and verifiable — Phase 1 re-run must then pass 28/28 with the
   guard active.
c) Wait for upstream fix, re-run Phase 1 unguarded.

## Reproduce

  python3 phase1.py            # full run (~2 min + one-time npm install)
  python3 phase1.py --skip-npm # skip vitest/tsc fixtures
