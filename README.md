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
