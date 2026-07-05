#!/usr/bin/env python3
"""Extract bash toolCall/toolResult pairs from pi session JSONLs and classify
them with detection logic ported 1:1 from techniques/{test-output,build,linter,git}.ts.

Writes per-technique corpus JSONL files (command, output, session, ts) to
bench/corpus/ and prints detection stats. Read-only w.r.t. sessions.
"""
import json
import os
import re
import sys
from pathlib import Path

SESSIONS = Path.home() / ".pi/agent/sessions"
OUT = Path(__file__).parent / "corpus"

# --- detection ports (keep in sync with techniques/*.ts) ---

TEST_COMMANDS = ["jest", "vitest", "pytest", "cargo test", "bun test", "go test",
                 "mocha", "ava", "tap"]
BUILD_COMMANDS = ["cargo build", "cargo check", "bun build", "npm run build",
                  "yarn build", "pnpm build", "tsc", "make", "cmake", "gradle",
                  "mvn", "go build", "go install", "python setup.py build",
                  "pip install"]
LINTER_COMMANDS = ["eslint", "prettier", "ruff", "pylint", "mypy", "flake8",
                   "black", "clippy", "golangci-lint"]
GIT_RE = re.compile(r"(?:^|&&\s*|\|\|\s*|;\s*|\|\s*)git\s+(diff|status|log|show|stash)(?:\s|$)", re.M)

TEST_RES = [re.compile(r"(?:^|[\s|;&])" + re.escape(tc) + r"(?:[\s|;&]|$)") for tc in TEST_COMMANDS]
LINT_RES = [re.compile(r"(?:^|[|;&]\s*)" + re.escape(lc) + r"(?:\s|$|[|;&])", re.M) for lc in LINTER_COMMANDS]


def classify(cmd: str):
    lower = cmd.lower()
    cats = []
    if any(r.search(lower) for r in TEST_RES):
        cats.append("test")
    if any(bc in lower for bc in BUILD_COMMANDS):
        cats.append("build")
    if any(r.search(lower) for r in LINT_RES):
        cats.append("linter")
    m = GIT_RE.search(cmd)
    if m:
        cats.append("git-" + m.group(1))
    return cats


def iter_pairs(path: Path):
    calls = {}  # id -> command
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
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
                        if isinstance(b, dict) and b.get("type") == "toolCall" and b.get("name") == "bash":
                            cmd = (b.get("arguments") or {}).get("command")
                            if isinstance(cmd, str):
                                calls[b.get("id")] = cmd
                elif role == "toolResult" and m.get("toolCallId") in calls:
                    txt = "".join(
                        b.get("text", "") for b in m.get("content") or []
                        if isinstance(b, dict) and b.get("type") == "text")
                    yield calls.pop(m["toolCallId"]), txt, e.get("timestamp")
    except OSError:
        return


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    writers = {}
    stats = {}          # cat -> [count, out_chars]
    total = [0, 0]      # pairs, out_chars
    files = sorted(SESSIONS.rglob("*.jsonl"))
    for i, f in enumerate(files):
        sess = str(f.relative_to(SESSIONS))
        for cmd, out, ts in iter_pairs(f):
            total[0] += 1
            total[1] += len(out)
            for cat in classify(cmd):
                s = stats.setdefault(cat, [0, 0])
                s[0] += 1
                s[1] += len(out)
                if cat not in writers:
                    writers[cat] = open(OUT / f"{cat}.jsonl", "w", encoding="utf-8")
                writers[cat].write(json.dumps(
                    {"command": cmd, "output": out, "session": sess, "ts": ts},
                    ensure_ascii=False) + "\n")
        if (i + 1) % 500 == 0:
            print(f"  ...{i+1}/{len(files)} files", file=sys.stderr)
    for w in writers.values():
        w.close()

    print(f"sessions scanned: {len(files)}")
    print(f"bash pairs: {total[0]}, output chars: {total[1]:,}")
    for cat in sorted(stats):
        c, ch = stats[cat]
        print(f"  {cat:12} {c:6} calls  {ch:>12,} chars  ({100*ch/max(total[1],1):.1f}% of bash output)")


if __name__ == "__main__":
    main()
