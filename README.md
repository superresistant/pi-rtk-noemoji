# pi-rtk-noemoji

Fork of [pi-rtk](https://github.com/mcowger/pi-rtk) by Matt Cowger. **Identical functionality, all emoji removed from output.** Plain text markers only (`[OK]`, `[ERROR]`, `[WARN]`, `PASS:`, `FAIL:`, `SKIP:`, etc.).

Everything else — config, commands, techniques, `rtk_configure` tool — is unchanged from upstream.

## Why

Emoji in tool output wastes tokens (multi-byte), renders inconsistently across terminals, and adds no information over plain text markers.

## Installation

```
pi install npm:pi-rtk-noemoji
```

Or in `~/.pi/agent/settings.json`:

```json
{
  "packages": [
    "npm:pi-rtk-noemoji"
  ]
}
```

## Configuration

Same as upstream. Create `~/.pi/agent/rtk-config.json`:

```json
{
  "enabled": true,
  "techniques": {
    "ansiStripping": true,
    "truncation": { "enabled": false },
    "sourceCodeFiltering": { "enabled": false },
    "smartTruncation": { "enabled": false },
    "testOutputAggregation": true,
    "buildOutputFiltering": true,
    "gitCompaction": false,
    "searchResultGrouping": false,
    "linterAggregation": true
  }
}
```

**Recommended safe config above**: only techniques that cannot break `edit` exact-match are enabled. Source code filtering is off — it strips comments/whitespace, causing the model to see different text than what's on disk.

## Commands

- `/rtk-stats` — token savings statistics
- `/rtk-on` / `/rtk-off` — enable/disable
- `/rtk-what` — show current config
- `/rtk-toggle-<technique>` — toggle individual techniques

## Output examples

Build success:
```
[OK] Build successful (12 units compiled)
```

Build errors:
```
[ERROR] 2 error(s):
error[E0308]: mismatched types
  --> src/main.rs:5:12

[WARN] 3 warning(s)
```

Test results:
```
Test Results:
   PASS: 42 passed
   FAIL: 2 failed
   SKIP: 1 skipped

   Failures:
   - FAIL test_something
     expected 1, got 2
```

## Known issues fixed in this fork

### `isSearchCommand` / `isLinterCommand`: substring false positives

`includes()` matches anywhere in the command string, not just at the command name position:

| Check | False positive examples |
|---|---|
| `includes("ag")` | `npm run agent`, `manage.py`, any path with "package" |
| `includes("find")` | paths containing "find", `findall()` calls |
| `includes("black")` | `blacklist`, any path with "black" |
| `includes("ruff")` | any path containing "ruff" |

When a false positive fires, the command's output is silently replaced with a reformatted search/linter summary — discarding the real output. `isTestCommand` had the same bug (bare `"test"` matching any command with "test" in it, silently destroying Python script output). **Fix**: regex matching at command position only (start of string or after `|`, `&&`, `;`).

### `isGitCommand`: `startsWith` never matched in practice

`startsWith("git status")` requires the command string to begin with `git`. Agents routinely prefix with a directory change: `cd /repo && git status`. Across 908 real git commands in session history, **0 matched** — gitCompaction was silently inert for all of them. **Fix**: regex matching `git <sub>` after chain operators (`&&`, `||`, `;`, `|`) as well as at start of string.

### `compactStatus`: corrupts verbose `git status` output

`compactStatus` expects porcelain format (`git status -s`). When called with verbose output (`git status` without flags), the parser misreads English prose as two-char status codes — `"Changes not staged for commit:"` becomes `status[0] = 'C'` → staged++, with filename `"anges not staged for commit:"`. Real modified files are not shown. **Fix**: detect verbose output on the first non-empty line and return `null` (pass-through).

### Source code filtering breaks `edit` tool

`sourceCodeFiltering` strips comments and normalizes whitespace when reading files. The agent sees modified text, but the `edit` tool requires exact match against the real file on disk — edits fail or silently corrupt content. **Recommendation: keep `sourceCodeFiltering` disabled** (it is off in the recommended config above).

### Truncation hides scan/data output

Default `truncation.maxChars: 10000` and `smartTruncation.maxLines: 200` are too aggressive for projects that read large JSON files, scan results, or verbose script output. Findings get silently dropped. **Recommendation: disable both for data-heavy projects.**

## Changes from upstream

All changes are in `techniques/*.ts` — emoji in generated output strings replaced with plain text. Regex detection patterns (for parsing test/build output) are untouched.

| Upstream | This fork |
|---|---|
| `✓` | `[OK]` |
| `❌` | `[ERROR]` |
| `⚠️` | `[WARN]` |
| `📋 Test Results:` | `Test Results:` |
| `✅ N passed` | `PASS: N passed` |
| `❌ N failed` | `FAIL: N failed` |
| `⏭️ N skipped` | `SKIP: N skipped` |
| `• failure` | `- failure` |
| `📄 file` | `> file` |
| `📌 branch` | `Branch: branch` |
| `🔍 N matches` | `N matches` |

## License

MIT — same as upstream.

## Credits

All credit to [Matt Cowger](https://github.com/mcowger) for the original [pi-rtk](https://github.com/mcowger/pi-rtk).
