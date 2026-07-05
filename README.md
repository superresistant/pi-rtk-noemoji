# pi-rtk-debunked

This started as [pi-rtk](https://github.com/mcowger/pi-rtk) with the emoji removed. It ended as a measurement project: every token-reduction technique in this space, replayed against complete real usage history. Nearly every claim died on contact with real data. One technique survived.

**The extension that remains does exactly one thing: strip ANSI escape sequences from bash tool output.** Everything else documented below was deleted, with proofs.

## Method

No synthetic benchmarks. Every technique was replayed against the full session history of a working pi setup: 3,765 sessions, 246,241 tool results, 599M chars of tool output (130k bash calls / 200M chars among them). Detection logic ran against real commands; filters ran against real outputs; safety was checked with planted-fact invariants and manual review samples; token counts via ttok. Scripts in `bench/`, one results file per investigation. Corpus data is session-derived and stays local (gitignored) — the scripts rebuild it from any pi session directory.

## Claims vs measurements

### Post-hoc output filtering (upstream pi-rtk's techniques) — `bench/RESULTS.md`

| Claim | Measurement |
|---|---|
| Test aggregation "preserves essential information" | Loses the failure signal on 9.4% of applied calls (clean pre-install data): vitest's `2 failed \| 8 passed` parses as *8 passed*. Failing runs reported as PASS. It ran live in this setup for a while: 758 stored session outputs are flattened PASS summaries. |
| Build filtering extracts what matters | Detection by substring: `tsc` fires on `tsconfig.json`, `make` on `make_article.py` (~25% false positives). Replaces vite chunk warnings and python unittest results with `[OK] Build successful (0 units compiled)`. |
| Git compaction condenses diffs safely | 62% of real `git diff` calls use `--stat`/`--check`/`--name-only`; their output contains no diff markers, so compaction returns an **empty string**. The nominal 83% "savings" was mostly deletion. |
| Linter aggregation | Matched 15 commands in the entire history. |
| Search grouping | Hooks the `grep` tool: called 0 times in 3,765 sessions. Dead code. |
| Source filtering, "60-90% reduction" | 6.0% real savings (comments are cheap). Alters 91.3% of source reads — each one breaks a subsequent `edit` exact-match. Chops code at `//` inside strings: `baseUrl: "https://api.anthropic.com",` → `baseUrl: "https:`. |
| Truncation keeps relevant context | Would have eaten 51M chars (25% of all bash output) of scan results and data. The harness already caps output. |

### Pre-execution command rewriting (rtk-ai/rtk binary) — `bench/rtk-eval/`

Architecturally sounder — it controls the invocation instead of guessing at text — so it earned a five-phase gated evaluation, including 80 live agent sessions (paired A/B, byte-identical fixtures, pre-registered thresholds).

| Claim | Measurement |
|---|---|
| "60-90% token reduction" | End-to-end cost on live paired trials: **-1%**. Final context: +5%. Formatting overhead exceeds savings on small outputs (`rtk tsc`: -46%, output got bigger). |
| Output safe to consume | `rtk git status --porcelain \| wc -l` returns 6 where raw returns 7 (trailing newline stripped); piped `rtk git diff` differs; `rtk ls` compacts even when piped. 52.8% of coverable real output feeds computation consumers — silent wrong numbers. |
| Broad coverage | True: 34.4% of 130k real commands rewrite, compound `cd && git` handled. After guarding the consumer hazard: 16.7% of bash output mass remains coverable. |
| Models handle it | True: gpt-5.5 consumed rtk formats transparently — 100% task success both arms, zero distrust re-queries, zero vocabulary leakage. The behavior fear is debunked in rtk's favor; the token claim is not. |

Verdict: stopped. Behavior clean, prize bounded at low single digits of total context, third-party binary in the execution path not justified.

### JSON re-encoding (TOON) — `bench/toon-eval/`

| Claim | Measurement |
|---|---|
| "30-60% savings on tabular JSON" | 16.4% tokens on real sweet-spot data (753 samples, 15M chars). Real tabular JSON is string-heavy; TOON only removes structure. |
| Lossless | Encoder emits output its own decoder rejects on 3.9% of real mixed JSON — strings containing CRLF or embedded JSON break row framing, silently. |
| Broadly applicable | Sweet spot is 6.5% of all tool output, concentrated in two data-heavy projects. Ceiling: ~1.1% of tool-output tokens. `python`/`jq` aggregation of those same files beats it at zero risk. |

### Prompt-side modes (terse-output prompts, YAGNI prompts)

Not evaluated here: legitimate axis, but they are prompt engineering, not output processing — and they belong in your own system prompt or skills, not in a dependency.

## What survived

**ANSI stripping.** Measured on pre-install months of raw history: 1.7% of bash output chars were ANSI escapes. Zero information loss by construction. Live-verified: post-install sessions contain zero strippable residue.

That is the whole extension: ~300 lines, one `tool_result` hook, `/rtk-stats`, `/rtk-on|off`, `/rtk-what`, `/rtk-clear`, `/rtk-toggle-ansiStripping`.

## The pattern behind the failures

1. **Real usage is already curated.** Agents pipe through `tail`/`head`, read selectively, aggregate with `jq`/`python`. Post-hoc filters mostly re-mangle outputs that were already small; savings claims assume nobody curates.
2. **Savings claims are measured on structure-heavy synthetic data.** Real outputs are string-heavy; the compressible fraction is smaller than advertised, everywhere.
3. **Silent information loss costs more than tokens.** A filter that reports failing tests as passing, or an off-by-one line count feeding a decision, destroys more value than any compression recovers. Every technique above fails silently, none fails loudly.
4. **Output has machine consumers, not just the model.** Pipes, `$( )`, redirects. Any rewriter that changes output format needs a consumer guard; none of the packages evaluated has one.

## Installation

```
pi install git:github.com/superresistant/pi-rtk-debunked
```

Config (optional — this is also the default): `~/.pi/agent/rtk-config.json`

```json
{ "enabled": true, "techniques": { "ansiStripping": true } }
```

## Reproduce

Every number above regenerates from any pi session directory:

```
python3 bench/extract.py            # corpus from session JSONLs
node --experimental-strip-types bench/replay.ts    # filter replay (needs v0.1.7 tree for deleted techniques)
python3 bench/survey.py             # ANSI audit, live-damage fingerprints
python3 bench/rtk-eval/phase0.py    # rtk rewrite coverage
python3 bench/rtk-eval/phase1.py    # seeded-fact fixtures
python3 bench/rtk-eval/phase2/run-trials.py  # live paired A/B
python3 bench/toon-eval/scan.py     # TOON addressable mass
```

## License

MIT — same as upstream.

## Credits

Matt Cowger for the original [pi-rtk](https://github.com/mcowger/pi-rtk), whose fork brought us here honestly: we came for fewer emoji and left with fewer illusions.
