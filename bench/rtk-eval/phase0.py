#!/usr/bin/env python3
"""Phase 0: coverage of `rtk rewrite` over all real bash commands.

Pass 1 (dump): scan session JSONLs, write all-commands.jsonl
               (command, output_chars, ts) for every bash toolCall/toolResult pair.
Pass 2 (rewrite): dedupe commands, run the pinned rtk binary on each unique
               command in an isolated HOME, aggregate coverage by call count
               and by output-char mass, break down by rtk target command.

Usage: python3 phase0.py [dump|rewrite|all]
"""
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
SESSIONS = Path.home() / ".pi/agent/sessions"
DUMP = HERE / "all-commands.jsonl"
RTK = HERE / "bin/rtk"
HOME = HERE / "home"
RESULTS = HERE / "phase0-results.json"


def dump():
    n = 0
    with open(DUMP, "w", encoding="utf-8") as out:
        for fpath in sorted(SESSIONS.rglob("*.jsonl")):
            calls = {}
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
                    if m.get("role") == "assistant":
                        for b in m.get("content") or []:
                            if isinstance(b, dict) and b.get("type") == "toolCall" and b.get("name") == "bash":
                                cmd = (b.get("arguments") or {}).get("command")
                                if isinstance(cmd, str):
                                    calls[b.get("id")] = cmd
                    elif m.get("role") == "toolResult" and m.get("toolCallId") in calls:
                        txt_len = sum(len(b.get("text", "")) for b in m.get("content") or []
                                      if isinstance(b, dict) and b.get("type") == "text")
                        out.write(json.dumps({"c": calls.pop(m["toolCallId"]),
                                              "o": txt_len,
                                              "t": (e.get("timestamp") or "")[:7]}) + "\n")
                        n += 1
    print(f"dumped {n} pairs")


def rewrite():
    # aggregate identical command strings
    agg = defaultdict(lambda: [0, 0])  # cmd -> [calls, out_chars]
    for line in open(DUMP, encoding="utf-8"):
        e = json.loads(line)
        a = agg[e["c"]]
        a[0] += 1
        a[1] += e["o"]
    print(f"unique commands: {len(agg)}")

    env = {"HOME": str(HOME), "PATH": "/usr/bin:/bin",
           "XDG_CONFIG_HOME": str(HOME / ".config"), "XDG_DATA_HOME": str(HOME / ".data")}
    def one(cmd):
        try:
            p = subprocess.run([str(RTK), "rewrite", cmd], capture_output=True,
                               text=True, timeout=10, env=env)
            out = p.stdout.strip()
            return cmd, (out if out and out != cmd else None)
        except (subprocess.TimeoutExpired, OSError):
            return cmd, None

    rewritten = {}  # cmd -> rewritten string
    with ThreadPoolExecutor(max_workers=8) as ex:
        for i, (cmd, out) in enumerate(ex.map(one, agg.keys(), chunksize=64)):
            if out:
                rewritten[cmd] = out
            if (i + 1) % 10000 == 0:
                print(f"  ...{i+1}/{len(agg)}", file=sys.stderr)

    tot_calls = sum(a[0] for a in agg.values())
    tot_chars = sum(a[1] for a in agg.values())
    rw_calls = sum(agg[c][0] for c in rewritten)
    rw_chars = sum(agg[c][1] for c in rewritten)

    # breakdown by first rtk target in the rewritten string
    by_target = defaultdict(lambda: [0, 0])
    for cmd, rw in rewritten.items():
        idx = rw.find("rtk ")
        target = rw[idx + 4:].split() if idx >= 0 else []
        key = target[0] if target else "?"
        if key == "git" and len(target) > 1:
            key = f"git-{target[1]}"
        t = by_target[key]
        t[0] += agg[cmd][0]
        t[1] += agg[cmd][1]

    res = {
        "rtk_version": "0.43.0",
        "total_calls": tot_calls, "total_out_chars": tot_chars,
        "unique_commands": len(agg), "unique_rewritten": len(rewritten),
        "rewritten_calls": rw_calls, "rewritten_out_chars": rw_chars,
        "call_coverage_pct": round(100 * rw_calls / tot_calls, 2),
        "char_coverage_pct": round(100 * rw_chars / tot_chars, 2),
        "by_target": {k: {"calls": v[0], "out_chars": v[1]}
                      for k, v in sorted(by_target.items(), key=lambda x: -x[1][1])},
    }
    RESULTS.write_text(json.dumps(res, indent=1))
    # sample rewrites for review
    with open(HERE / "phase0-sample-rewrites.txt", "w") as f:
        for i, (cmd, rw) in enumerate(rewritten.items()):
            if i >= 200:
                break
            f.write(f"RAW: {cmd[:160]}\nRTK: {rw[:160]}\n\n")

    print(f"calls: {rw_calls}/{tot_calls} rewritten ({res['call_coverage_pct']}%)")
    print(f"output mass: {rw_chars:,}/{tot_chars:,} chars ({res['char_coverage_pct']}%)")
    print("top targets by output mass:")
    for k, v in list(res["by_target"].items())[:15]:
        print(f"  {k:14} calls={v['calls']:6}  chars={v['out_chars']:>12,}")


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    if arg in ("dump", "all"):
        dump()
    if arg in ("rewrite", "all"):
        rewrite()
