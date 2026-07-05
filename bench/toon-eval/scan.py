#!/usr/bin/env python3
"""TOON evaluation, track A: how much real tool output is JSON, and how much
of that is TOON's sweet spot (uniform arrays of objects)?

Scans all session JSONLs; for every toolResult text (any tool):
  - strict JSON detection: stripped text parses as JSON ({ or [ start),
    or JSONL (>= 3 lines, each parses as an object)
  - classification:
      sweet   top-level uniform array of flat objects (same key sets, scalar
              values), or object with one such array >= 80% of mass
      mixed   parses but nested/non-uniform
  - per-tool aggregation by chars
Writes samples of sweet/mixed JSON (up to caps) for the encode benchmark.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

SESSIONS = Path.home() / ".pi/agent/sessions"
OUT = Path(__file__).parent / "samples"
SWEET_CAP = 15_000_000
MIXED_CAP = 15_000_000


def classify(obj):
    def flat_uniform(arr):
        if not isinstance(arr, list) or len(arr) < 3:
            return False
        if not all(isinstance(x, dict) for x in arr):
            return False
        keys = set(arr[0].keys())
        if not keys:
            return False
        for x in arr:
            if set(x.keys()) != keys:
                return False
            if any(isinstance(v, (dict, list)) for v in x.values()):
                return False
        return True

    if flat_uniform(obj):
        return "sweet"
    if isinstance(obj, dict):
        total = len(json.dumps(obj))
        for v in obj.values():
            if flat_uniform(v) and len(json.dumps(v)) >= 0.8 * total:
                return "sweet"
    return "mixed"


def detect(text):
    s = text.strip()
    if not s:
        return None, None
    if s[0] in "{[":
        try:
            return "json", json.loads(s)
        except (json.JSONDecodeError, RecursionError):
            pass
    lines = [l for l in s.split("\n") if l.strip()]
    if len(lines) >= 3:
        try:
            objs = [json.loads(l) for l in lines[:200]]
            if all(isinstance(o, dict) for o in objs):
                return "jsonl", objs
        except (json.JSONDecodeError, RecursionError):
            pass
    return None, None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sweet_f = open(OUT / "sweet.jsonl", "w", encoding="utf-8")
    mixed_f = open(OUT / "mixed.jsonl", "w", encoding="utf-8")
    caps = {"sweet": [0, SWEET_CAP, sweet_f], "mixed": [0, MIXED_CAP, mixed_f]}

    tool_of = {}
    by_tool = defaultdict(lambda: [0, 0, 0, 0])  # results, chars, json_chars, sweet_chars
    kind_stats = defaultdict(lambda: [0, 0])

    files = sorted(SESSIONS.rglob("*.jsonl"))
    for i, f in enumerate(files):
        calls = {}
        try:
            fh = open(f, encoding="utf-8", errors="replace")
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
                if m.get("role") == "assistant":
                    for b in m.get("content") or []:
                        if isinstance(b, dict) and b.get("type") == "toolCall":
                            calls[b.get("id")] = b.get("name") or "?"
                elif m.get("role") == "toolResult":
                    tool = calls.pop(m.get("toolCallId"), "?")
                    txt = "".join(b.get("text", "") for b in m.get("content") or []
                                  if isinstance(b, dict) and b.get("type") == "text")
                    st = by_tool[tool]
                    st[0] += 1
                    st[1] += len(txt)
                    kind, obj = detect(txt)
                    if kind:
                        st[2] += len(txt)
                        cls = classify(obj)
                        kind_stats[(kind, cls)][0] += 1
                        kind_stats[(kind, cls)][1] += len(txt)
                        if cls == "sweet":
                            st[3] += len(txt)
                        cap = caps[cls]
                        if cap[0] + len(txt) <= cap[1]:
                            cap[0] += len(txt)
                            cap[2].write(json.dumps({"tool": tool, "text": txt}) + "\n")
        if (i + 1) % 500 == 0:
            print(f"  ...{i+1}/{len(files)}", file=sys.stderr)

    sweet_f.close()
    mixed_f.close()

    tot = [sum(v[k] for v in by_tool.values()) for k in range(4)]
    print(f"tool results: {tot[0]}, chars {tot[1]:,}")
    print(f"JSON chars: {tot[2]:,} ({100*tot[2]/max(tot[1],1):.1f}% of all tool output)")
    print(f"TOON-sweet chars: {tot[3]:,} ({100*tot[3]/max(tot[1],1):.2f}% of all tool output)")
    print("\nby kind/class:")
    for (kind, cls), (n, ch) in sorted(kind_stats.items(), key=lambda x: -x[1][1]):
        print(f"  {kind:5} {cls:6} n={n:6}  chars={ch:>12,}")
    print("\ntop tools by JSON chars:")
    rows = sorted(by_tool.items(), key=lambda x: -x[1][2])[:12]
    for tool, (n, ch, jch, sch) in rows:
        if jch:
            print(f"  {tool:16} results={n:6}  chars={ch:>12,}  json={jch:>12,}  sweet={sch:>10,}")


if __name__ == "__main__":
    main()
