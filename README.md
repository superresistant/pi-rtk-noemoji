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

### Command detection was too broad (upstream bug)

Several `is*Command` functions used `command.includes("keyword")` to detect whether a bash command was a build/test/search/linter invocation. This caused false positives:

- **`isSearchCommand`**: `includes("ag")` matched "agent", "package", "manage". `includes("find")` matched "findall", paths containing "find". Any command accidentally classified as a search command had its output reformatted and truncated to 50 results.
- **`isLinterCommand`**: `includes("black")` matched "blacklist". `includes("ruff")` matched any command with "ruff" as a substring.
- **`isTestCommand`**: bare `"test"` in TEST_COMMANDS matched any command containing the word "test", replacing the entire output with a test summary. This silently destroyed Python script output whenever a line contained the word "ok" (counted as a passed test).

**Fix**: removed bare `"test"` from TEST_COMMANDS. Changed `isSearchCommand` and `isLinterCommand` to match command names only at command position (start of line or after `|`, `&&`, `;`), not as substrings.

### Source code filtering breaks `edit` tool

The `sourceCodeFiltering` technique strips comments and normalizes whitespace when reading files. The agent then sees modified text, but the `edit` tool requires exact match against the real file content. Edits fail silently or target the wrong text. **Recommendation: keep `sourceCodeFiltering` disabled.**

### Truncation hides scan/data output

Default `truncation.maxChars: 10000` (10KB) and `smartTruncation.maxLines: 200` are too aggressive for projects that read large JSON files, scan results, or verbose script output. Findings get silently dropped. **Recommendation: disable both for data-heavy projects.**

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
