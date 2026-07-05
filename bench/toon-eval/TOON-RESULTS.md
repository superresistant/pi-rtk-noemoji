# TOON evaluation — real technique, marginal prize, lossy edges. Verdict: skip

Date: 2026-07-05. Trigger: @xynogen/pix-optimizer's TOON integration (the one
technique in that package not already known or already debunked). Method: same
corpus discipline as the rtk eval. Library @toon-format/toon@2.3.0 installed
locally in bench/toon-eval (never global), samples extracted from all real
session toolResults.

## Track A: how much of our real tool output is TOON-addressable?

scan.py over 246,241 toolResults (599.1M chars, all tools):
  JSON output:        51.4M chars  (8.6% of all tool output)
  TOON sweet spot:    38.8M chars  (6.5%)  — uniform arrays of flat objects
  (by kind: jsonl-sweet 36.7M dominates; bash contributes only 6.7M JSON)

Attribution (path pass): the sweet mass is concentrated in two data-heavy
projects — fine-tuning batch files (training-batch JSONL, ~90-170K each,
hundreds of files) and research data artifacts.
Not a general-workflow phenomenon. And for those reads the superior existing
remedy is sampling/aggregation (python/jq/head) — reading a 90K batch file
wholesale is the mistake; compressing that mistake by 16% is not the fix.

## Track B: measured savings and fidelity on real samples (encode-bench.mjs)

  sweet (753 samples, 15.0M chars): chars -4.3%, tokens -16.4% (ttok),
        encode failures 0, roundtrip failures 0
  mixed (4,954 samples, 12.6M chars): chars -12.2%, tokens -14.9%,
        roundtrip FAILURES 195/4954 (3.9%)

The 30-60% savings claim does not survive contact with real data: our
tabular JSON is string-heavy, and TOON only removes structural overhead.
16.4% tokens on the sweet spot is the honest number.

Fidelity: the roundtrip failures are TOON's own encoder emitting output its
own decoder rejects — real string values containing CRLF (email headers),
embedded JSON, or bracket-like text break row framing (ToonDecodeError:
"Unexpected content between bracket segment and colon"). Encoding succeeds
silently; the ambiguity lands on the reader. A model reading TOON faces the
same misframing risk on such rows. Uniform flat scalar rows (true sweet
spot) showed zero failures.

## Ceiling math

6.5% of tool output x 16.4% token savings = ~1.1% of total tool-output
tokens, assuming perfect application to every sweet read — concentrated in
two projects, with a better existing remedy, and a 3.9% silent-ambiguity
rate the moment data strays from flat scalars.

## Verdict

Skip. No extension, no dependency, no prompt nudge. The pix-optimizer
integration would not even fire on our real usage (its nudge triggers only
when the USER's prompt mentions JSON; our JSON mass flows through mid-task
reads). If anything is worth doing it is a habit note where the mass lives
(ultimate-loop / data-analysis work): aggregate uniform JSONL with
python/jq instead of reading files wholesale — that dominates TOON's entire
benefit at zero risk.

## Reproduce

  python3 scan.py            # full corpus scan (~5 min), writes samples/
  node encode-bench.mjs      # savings + roundtrip on samples
  ttok < samples/sweet-raw.txt ; ttok < samples/sweet-toon.txt
