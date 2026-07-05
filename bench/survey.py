#!/usr/bin/env python3
"""Survey pass 2: data for the surviving techniques + ansiStripping audit.

Collects in one scan of ~/.pi/agent/sessions:
  A. grep-tool corpus            -> corpus/grep-tool.jsonl   (replayed by replay2.ts)
  B. read-tool source-file corpus-> corpus/read-source.jsonl (capped, deterministic)
  C. ANSI stats on bash outputs by month (regexes ported from techniques/ansi.ts)
  D. live-damage fingerprints of the deleted techniques in stored outputs
  E. bash outputs > truncation.maxChars (10000) — what truncation would eat
Read-only w.r.t. sessions.
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

SESSIONS = Path.home() / ".pi/agent/sessions"
OUT = Path(__file__).parent / "corpus"
READ_CAP_CHARS = 80_000_000  # cap stored read corpus

SRC_EXT = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".py", ".pyw", ".rs", ".go",
           ".java", ".c", ".h", ".cpp", ".hpp", ".cc"}

ANSI_RES = [re.compile(r"\x1b\[[0-9;]*[a-zA-Z]"),
            re.compile(r"\x1b\][0-9;]*(?:\x07|\x1b\\)"),
            re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")]

FP_BUILD = "Build successful (0 units compiled)"
FP_TEST = re.compile(r"^Test Results:\n   PASS: \d+ passed", re.M)


def strip_ansi(t):
    for r in ANSI_RES:
        t = r.sub("", t)
    return t


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    grep_f = open(OUT / "grep-tool.jsonl", "w", encoding="utf-8")
    read_f = open(OUT / "read-source.jsonl", "w", encoding="utf-8")
    read_stored = 0

    tool_counts = defaultdict(int)
    # ansi[month] = [n_outputs, n_with_esc, chars, chars_after_strip]
    ansi = defaultdict(lambda: [0, 0, 0, 0])
    fp_build = fp_test = 0
    big_bash = [0, 0]          # count, chars beyond 10000 each
    read_src = [0, 0]          # count, chars (all, not just stored)

    files = sorted(SESSIONS.rglob("*.jsonl"))
    for i, fpath in enumerate(files):
        calls = {}  # id -> (tool, arg)
        try:
            fh = open(fpath, encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(e, dict):
                    continue
                m = e.get("message")
                if not isinstance(m, dict):
                    continue
                role = m.get("role")
                if role == "assistant":
                    for b in m.get("content") or []:
                        if isinstance(b, dict) and b.get("type") == "toolCall":
                            name = b.get("name")
                            tool_counts[name] += 1
                            a = b.get("arguments") or {}
                            if name == "bash":
                                calls[b.get("id")] = ("bash", a.get("command"))
                            elif name == "grep":
                                calls[b.get("id")] = ("grep", json.dumps(a))
                            elif name == "read":
                                calls[b.get("id")] = ("read", a.get("path"))
                elif role == "toolResult":
                    got = calls.pop(m.get("toolCallId"), None)
                    if not got:
                        continue
                    tool, arg = got
                    txt = "".join(b.get("text", "") for b in m.get("content") or []
                                  if isinstance(b, dict) and b.get("type") == "text")
                    ts = e.get("timestamp") or ""
                    month = ts[:7]
                    if tool == "bash":
                        s = ansi[month]
                        s[0] += 1
                        s[2] += len(txt)
                        if "\x1b" in txt:
                            s[1] += 1
                            s[3] += len(strip_ansi(txt))
                        else:
                            s[3] += len(txt)
                        if FP_BUILD in txt:
                            fp_build += 1
                        if FP_TEST.search(txt):
                            fp_test += 1
                        if len(txt) > 10000:
                            big_bash[0] += 1
                            big_bash[1] += len(txt) - 10000
                    elif tool == "grep":
                        grep_f.write(json.dumps(
                            {"args": arg, "output": txt, "ts": ts,
                             "session": str(fpath.relative_to(SESSIONS))},
                            ensure_ascii=False) + "\n")
                    elif tool == "read" and arg:
                        ext = "." + arg.rsplit(".", 1)[-1].lower() if "." in arg else ""
                        if ext in SRC_EXT:
                            read_src[0] += 1
                            read_src[1] += len(txt)
                            nonlocal_stored = read_stored + len(txt)
                            if nonlocal_stored <= READ_CAP_CHARS:
                                read_stored = nonlocal_stored
                                read_f.write(json.dumps(
                                    {"path": arg, "output": txt, "ts": ts,
                                     "session": str(fpath.relative_to(SESSIONS))},
                                    ensure_ascii=False) + "\n")
        if (i + 1) % 500 == 0:
            print(f"  ...{i+1}/{len(files)}", file=sys.stderr)

    grep_f.close()
    read_f.close()

    print("tool call counts (top):")
    for name, c in sorted(tool_counts.items(), key=lambda x: -x[1])[:12]:
        print(f"  {name:20} {c}")

    print("\nANSI on bash outputs by month (n, with-ESC, chars, saved-by-strip):")
    for month in sorted(ansi):
        n, esc, ch, after = ansi[month]
        print(f"  {month}  n={n:6}  esc={esc:5}  chars={ch:>12,}  saved={ch-after:>10,} ({100*(ch-after)/max(ch,1):.2f}%)")

    print(f"\nlive-damage fingerprints in stored bash outputs: build-oneliner={fp_build}, test-pass-summary={fp_test}")
    print(f"bash outputs >10000 chars: {big_bash[0]}, chars beyond cap: {big_bash[1]:,} (what truncation would eat)")
    print(f"read source-file results: {read_src[0]}, {read_src[1]:,} chars (stored {read_stored:,})")


if __name__ == "__main__":
    main()
