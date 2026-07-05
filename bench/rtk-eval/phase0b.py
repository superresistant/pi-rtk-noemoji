#!/usr/bin/env python3
"""Phase 0b: full rewrite mapping + pipe-consumer quantification + purity check.

1. Rerun `rtk rewrite` over all unique commands, this time persisting the full
   mapping to rewrites.jsonl.
2. For every rewritten command, determine whether the rtk-wrapped segment's
   output feeds another program (pipe within segment), and classify the first
   consumer as display (head/tail/cat/less/more) or computation (everything
   else: wc, jq, xargs, grep, awk, sed, sort, ...).
3. Purity check: strace a command sample and require zero network syscalls
   (unshare -rn is blocked for unprivileged users on Ubuntu 24.04).
"""
import json
import random
import re
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).parent
DUMP = HERE / "all-commands.jsonl"
RTK = HERE / "bin/rtk"
HOME = HERE / "home"
REWRITES = HERE / "rewrites.jsonl"

ENV = {"HOME": str(HOME), "PATH": "/usr/bin:/bin",
       "XDG_CONFIG_HOME": str(HOME / ".config"), "XDG_DATA_HOME": str(HOME / ".data")}
DISPLAY = {"head", "tail", "cat", "less", "more"}
SEG_SPLIT = re.compile(r"&&|\|\||;")


def load_agg():
    agg = defaultdict(lambda: [0, 0])
    for line in open(DUMP, encoding="utf-8"):
        e = json.loads(line)
        a = agg[e["c"]]
        a[0] += 1
        a[1] += e["o"]
    return agg


def rewrite_all(agg):
    def one(cmd):
        try:
            p = subprocess.run([str(RTK), "rewrite", cmd], capture_output=True,
                               text=True, timeout=10, env=ENV)
            out = p.stdout.strip()
            return cmd, (out if out and out != cmd else None)
        except (subprocess.TimeoutExpired, OSError):
            return cmd, None

    n = 0
    with open(REWRITES, "w", encoding="utf-8") as f, ThreadPoolExecutor(max_workers=8) as ex:
        for i, (cmd, out) in enumerate(ex.map(one, agg.keys(), chunksize=64)):
            if out:
                f.write(json.dumps({"c": cmd, "rw": out,
                                    "calls": agg[cmd][0], "chars": agg[cmd][1]}) + "\n")
                n += 1
            if (i + 1) % 20000 == 0:
                print(f"  ...{i+1}/{len(agg)}", file=sys.stderr)
    print(f"rewritten unique: {n}")


def consumer_class(rw):
    """Return (feeds_consumer, kind, first_consumer) for a rewritten command."""
    for seg in SEG_SPLIT.split(rw):
        idx = seg.find("rtk ")
        if idx == -1:
            continue
        after = seg[idx:]
        if "|" not in after:
            continue
        first = after.split("|", 1)[1].strip()
        tok = first.split()[0] if first.split() else "?"
        tok = tok.lstrip("&")  # 2>&1| artifacts
        if tok in DISPLAY:
            return True, "display", tok
        return True, "computation", tok
    return False, None, None


def analyze():
    stats = defaultdict(lambda: [0, 0])  # kind -> [calls, chars]
    consumers = defaultdict(int)
    tot = [0, 0]
    for line in open(REWRITES, encoding="utf-8"):
        e = json.loads(line)
        tot[0] += e["calls"]
        tot[1] += e["chars"]
        feeds, kind, tok = consumer_class(e["rw"])
        key = kind if feeds else "no-pipe"
        stats[key][0] += e["calls"]
        stats[key][1] += e["chars"]
        if kind == "computation":
            consumers[tok] += e["calls"]
    print(f"\nrewritten calls total: {tot[0]}, chars {tot[1]:,}")
    for k in ("no-pipe", "display", "computation"):
        c, ch = stats.get(k, [0, 0])
        print(f"  {k:12} calls={c:6} ({100*c/max(tot[0],1):.1f}%)  chars={ch:>12,} ({100*ch/max(tot[1],1):.1f}%)")
    print("top computation consumers (by calls):")
    for tok, c in sorted(consumers.items(), key=lambda x: -x[1])[:12]:
        print(f"  {tok:12} {c}")


def purity():
    cmds = [json.loads(l)["c"] for l in open(REWRITES, encoding="utf-8")]
    random.seed(42)
    sample = random.sample(cmds, min(60, len(cmds)))
    hits = 0
    for cmd in sample:
        subprocess.run(["strace", "-f", "-e", "trace=network", "-o", "/tmp/rtk-trace.txt",
                        str(RTK), "rewrite", cmd], capture_output=True, timeout=15, env=ENV)
        trace = Path("/tmp/rtk-trace.txt").read_text()
        hits += sum(1 for l in trace.splitlines()
                    if any(s in l for s in ("socket(", "connect(", "sendto(", "sendmsg(", "recvfrom(")))
    print(f"\npurity: {len(sample)} rewrites straced, network syscalls: {hits}")


if __name__ == "__main__":
    agg = load_agg()
    if not REWRITES.exists() or "force" in sys.argv:
        rewrite_all(agg)
    analyze()
    purity()
