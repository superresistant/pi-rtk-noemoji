# Benchmark: candidate techniques replayed on real session history

Date: 2026-07-05. Method: bench/extract.py scans all pi session JSONLs
(~/.pi/agent/sessions, 3765 files, 2.6 GB), pairs every bash toolCall with its
toolResult (130,101 pairs, 200.0M chars of output), classifies commands with
detection logic ported 1:1 from techniques/*.ts, writes per-technique corpora
to bench/corpus/ (gitignored). bench/replay.ts (node --experimental-strip-types)
then runs the real technique implementations over each corpus and checks
safety invariants. Review samples: bench/corpus/review-*.jsonl (30 random
before/after pairs each).

## Verdicts

testOutputAggregation: UNSAFE. 1407 matched calls, filter applied to 1074.
96.3% char savings BUT 174/1074 (16%) lose the failure signal: vitest prints
"Tests 2 failed | 8 passed (10)" which no TEST_RESULT_PATTERNS parses, so the
summary reports "PASS: 8 passed" and hides the failures. vitest is the dominant
runner in this history. An agent seeing the filtered output believes failing
tests pass. Disqualified as implemented.
Contamination split (bench/legacy/split.ts, cutoff 2026-02-28 = install date
of the live filters): pre-install (raw outputs, clean data): 488 entries,
46 violations = 9.4% of applied, 96.1% savings. Post-install window (outputs
possibly already filtered live): 21.8%. The defensible violation rate is the
pre-install 9.4%; the 16% headline mixes both windows. Verdict unchanged —
any failure-signal loss disqualifies.

buildOutputFiltering: UNSAFE + broken detection. isBuildCommand still uses
includes() (the anchored-detection fix of v0.1.x covered git/test/linter, not
build): "tsc" fires on any tsconfig.json mention (364 substring-only hits of
1795), "make" on make_article.py / Makefile text (413/870), "mvn" on base64
blobs (4/4). ~25% false positives overall, each replacing real output with
"[OK] Build successful (0 units compiled)". In manual review 16/30 applied
calls destroyed meaningful output (vite chunk-size warnings, python unittest
results matched via "make"). 1070/4177 outputs got LONGER after filtering.
Disqualified as implemented.

linterAggregation: IRRELEVANT here. 15 matching calls in the entire history
(8.5K chars total). Zero payoff; not worth the risk surface. Keep off.

gitCompaction: UNSAFE for diff, marginal for the rest.
  git-diff: 1449 calls, 5.4M chars, nominal 83.4% savings — but 897/1449 (62%)
  use summary flags (--stat 583, --check 262, --name-only 36, ...) whose output
  contains no "diff --git"/"@@" lines, so compactDiff returns an EMPTY STRING:
  total silent data loss. The nominal savings figure is mostly deletion.
  git-status: verbose guard works; but --short output (close to porcelain)
  parses with an empty "Branch:" header and grew the output in 5/30 review
  pairs (269/1549 overall).
  git-log: 44.5% savings on 546 applied calls (0.65M chars) — modest.

## Method caveats (added after critical review, same day)

1. Corpus contamination: sessions from 2026-02-28 onward were recorded with
   test/build/linter filters LIVE, so part of the round-1 corpora is
   post-filter text. Rates on mixed windows are indicative, not exact; the
   test split above gives the clean number. Verdicts are unaffected (they
   rest on categorical failures, mostly evidenced from pre-install data).
2. Oracle strength is uneven: the test invariant is strong; the build
   invariant only checked that error lines resurface — the real build harm
   (destroying non-build and success output) was caught by manual review,
   not by the "0 violations" stat. Do not read invariant counts across
   techniques as comparable.
3. Review/token samples were drawn with a biased shuffle (sort by random
   comparator; replay.ts now uses seeded Fisher-Yates) and the round-2 read
   corpus fills in directory order (alphabetical by project) up to the 80M
   cap — not a uniform sample. Effect sizes are large enough that neither
   bias plausibly flips a verdict.

## Token measurements (ttok on the concatenated sample pairs)

  test        53,084 ->   2,274  (95.7% saved)   vs 96.3% chars
  build       42,092 ->   2,000  (95.2%)
  linter       2,445 ->     149  (93.9%)
  git-status  59,396 ->   9,113  (84.7%)
  git-diff   234,109 ->  38,978  (83.4%)         identical to chars
  git-log     86,744 ->  37,901  (56.3%)
  source     160,023 -> 108,446  (32.2%)         vs 37.6% chars

Char-based savings track token-based savings within a few points; char
figures elsewhere in this file can be read as token-representative.

## Structural findings

1. Existing discipline already pipes big outputs through tail/head; the
   corpora are full of pre-curated small outputs, which is why "filtered
   longer than original" happens at all. No technique has a minimum-size gate
   (index.ts applies filters to every bash result).
2. Ceiling: even perfect implementations of all four cover ~12M of 200M bash
   output chars (~6%), and bash output is itself a minority of context vs
   file reads. Marginal upside, correctness downside.

## Recommendation (applied: all four stay off)

Keep only ansiStripping enabled. If any technique is ever worth rescuing it is
gitCompaction restricted to plain `git diff` (no summary flags) + `git status
--porcelain` only + a minimum-output-size gate — a rewrite, to attempt only if
real need appears. test aggregation would additionally need vitest format
support and is inherently risky (it hides exactly what the agent asked to see).

# Benchmark round 2: surviving techniques + ansiStripping audit (2026-07-05)

Method: bench/survey.py (single pass over all sessions) + bench/replay2.ts
(read-tool corpus through the real filterSourceCode/smartTruncate code).

searchResultGrouping: DEAD CODE. It hooks the `grep` tool's results; the grep
tool was called 0 times across all 3765 sessions (130,317 bash / 45,035 read /
24,223 edit calls; searches go through bash rg). Never fired once. Deleted.

sourceCodeFiltering + smartTruncation: UNSAFE, replayed on 15,731 real
source-file reads (80M chars): filterMinimal alters 91.3% of reads — each one
breaks a subsequent edit exact-match — for only 6.0% char savings. Worse,
comment stripping uses indexOf("//") which chops code at protocol slashes:
1,484 reads (4,754 occurrences) lose URL text, e.g.
`baseUrl: "https://api.anthropic.com",` -> `baseUrl: "https:`. That is code
corruption, not compression. smartTruncate reaches 37.6% savings only by
dropping file content wholesale (3,077 reads > 200 lines). Deleted.

truncation (maxChars 10000): 3,908 real bash outputs exceed the cap; it would
have eaten 51.1M chars (25% of all bash output) — scan results, data dumps.
pi's harness already caps tool output at 50KB. Deleted.

ansiStripping: KEEP — the only technique that survives measurement.
Pre-install months show the true raw value: 2026-02 (mostly pre-install)
914/31,819 bash outputs contained ESC, stripping saved 570,791 chars (1.71% of
bash output that month). Post-install months show saved=0 residual — live
stripping is working (leftover ESC bytes are sequences outside the regex).
Zero information loss by construction.

Live-damage confirmation of the round-1 deletions: the broken filters were
enabled in production 2026-02-28 until the config was reduced to ansi-only.
Stored session outputs contain 758 test outputs reduced to "Test Results:
PASS: N passed" summaries and 252 build outputs reduced to the
"[OK] Build successful (0 units compiled)" one-liner. The vitest
failure-hiding bug was live during that window.

Caveat on round-1 numbers: outputs recorded while those filters were live are
post-filter text, so round-1 savings/violation rates for the affected window
underestimate raw behavior; the violation examples cited are from pre-install
sessions (raw).

## Reproduce

  python3 bench/extract.py                         # rebuild corpora (read-only scan)
  node --experimental-strip-types bench/replay.ts  # replay + invariants + samples

  python3 bench/survey.py                          # round 2: grep/read corpora + ANSI audit
  node --experimental-strip-types bench/replay2.ts # round 2: source filtering replay

Note: all techniques except ansiStripping were deleted from the tree after
these benchmarks (same day). bench/replay.ts and bench/replay2.ts import the
deleted files, so the replay steps only run on the v0.1.7 tag
(`git checkout v0.1.7 -- techniques` restores them temporarily). extract.py
and survey.py are self-contained and still work.
