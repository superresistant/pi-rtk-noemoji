# Phase 2 results: live behavioral A/B — behavior PASS, token gate FAIL, STOP per rule

Date: 2026-07-05. 64 paired gpt-5.5 trials (4 tasks x 8 pairs x 2 arms) + 16
exploratory gpt-5.3-codex-spark trials. Real pi sessions (isolated agent dir,
`-a` trust, `-p @task.md`, tmux, concurrency 4), byte-identical fixture pairs,
guarded probe extension in the rtk arm. All 80 sessions exited 0. Raw data:
phase2-results-{g55,spark}.json; harness: make-fixtures.py, run-trials.py,
analyze.py.

## Pre-registered gates (gpt-5.5)

(a) task success:        PASS  — 32/32 control, 32/32 rtk (100% both arms)
(b) tokens -15% median:  FAIL  — final context +5%, end-to-end cost -1%
(c) re-query < 10%:      PASS  — zero rewritten-then-raw re-query patterns;
                                 duplicate bash calls symmetric across arms
                                 (legitimate test re-runs in fixtest)
(d) wrong answers from compaction: PASS — zero
    rtk leakage into model-authored text/files: zero

Per the pre-registered rule (fail any gate -> stop): Phase 2 verdict is STOP.

## What the run actually established

The feared behavioral failure mode did not materialize. gpt-5.5 consumed
rtk-formatted output transparently: correct answers from `rtk git status`
porcelain-style views, `rtk vitest` failure listings, `rtk ls` trees; no
distrust loops, no confusion prose, no vocabulary leakage, slightly FEWER
turns in the rtk arm on the hardest task (fixtest: 9 vs 10 median). Rewrite
rates in-session: 50-100% of bash calls per task.

The token gate failed for a structural reason, not a behavioral one: the
fixtures are micro-tasks (1-5 bash calls, small outputs). Compaction value
scales with output volume; on outputs this small, rtk's formatting overhead
and stack-trace retention wash out the wins (fixtest cost +42% is exploration
noise: distributions overlap 2669-6043 vs 2880-6677). The only task with
consistent volume (diffsum) showed a consistent -8% cost / -3% context win.
Micro-fixtures cannot exhibit the 33.5M chars of guarded-covered mass that
real history contains.

## Spark arm (exploratory, non-gating)

finddef 4/4 both arms. gitstate 0/8 BOTH arms — identical misclassification
(staged vs modified) in control and rtk, format followed, facts wrong: model
capability failure, perfectly symmetric. rtk neither rescues nor further
breaks a weak model. No crashes, no tool-use breakdown with the extension.

## Honest bound on the prize

Guarded coverage of real history: 33.5M chars = 16.7% of all bash output.
At the 60-80% compaction seen on volume outputs, ceiling ~10-13% of bash
output mass. Bash output is itself a minority of total tool output (source
reads alone were 88M chars). So the whole rtk apparatus, guarded, optimizes
low single digits of total context on our real usage profile — before
counting the pi harness's own 50KB truncation which already caps the worst
offenders.

## Options from here

1. Accept STOP: do not adopt. Benefit bounded at low single digits of
   context, unproven in-vivo, at the cost of a third-party binary in the
   execution path.
2. Phase 2b: volume-realistic fixtures (large diffs, hundreds of search
   hits, long suites) to give the token gate a fair shot; re-run.
3. Phase 3 (offline, no LLM cost): re-execute real read-only commands from
   history on cloned real repos, both ways; measure the actual token mass
   saved. Decide from data instead of fixture design.

## Reproduce

  python3 make-fixtures.py
  python3 run-trials.py --tasks fixtest,gitstate,finddef,diffsum --pairs 8 --label g55
  python3 run-trials.py --tasks gitstate,finddef --pairs 4 --model openai-codex/gpt-5.3-codex-spark --label spark
  python3 analyze.py --label g55
