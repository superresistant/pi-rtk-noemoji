#!/usr/bin/env python3
"""Phase 2 analyzer: checkers + session mining + gate verdict.

Usage: python3 analyze.py [--label g55]
Reads /tmp/rtk-phase2/trials/p2<label>-*, the shared agent sessions dir, and
truth.json. Writes phase2-results-<label>.json next to this script.
"""
import argparse
import json
import re
import statistics
import subprocess
from collections import defaultdict
from pathlib import Path

ROOT = Path("/tmp/rtk-phase2")
HERE = Path(__file__).resolve().parent
TRUTH = json.loads((ROOT / "truth.json").read_text())
SESS = ROOT / "agent/sessions"
ENV = {"HOME": str(ROOT / "githome"), "PATH": "/usr/local/bin:/usr/bin:/bin",
       "npm_config_cache": str(Path.home() / ".npm")}


def reply_of(tdir: Path) -> str:
    try:
        return (tdir / "out.log").read_text(errors="replace").strip()
    except OSError:
        return ""


def check_fixtest(tdir, reply):
    repo = tdir / "repo"
    p = subprocess.run(["bash", "-c", "npx vitest run >/dev/null 2>&1; echo $?"],
                       cwd=repo, env=ENV, capture_output=True, text=True, timeout=180)
    green = p.stdout.strip() == "0"
    tests_untouched = all(
        subprocess.run(["diff", "-q", str(ROOT / "templates/fixtest/repo" / t), str(repo / t)],
                       capture_output=True).returncode == 0
        for t in TRUTH["fixtest"]["test_files"])
    return green and tests_untouched


def parse_list(line):
    return {p.strip().strip(",") for p in line.split(":", 1)[1].split(",") if p.strip()}


def check_gitstate(tdir, reply):
    got = {}
    for line in reply.splitlines():
        m = re.match(r"^(staged|modified|deleted|untracked)\s*:", line.strip(), re.I)
        if m:
            got[m.group(1).lower()] = parse_list(line)
    t = TRUTH["gitstate"]
    return all(got.get(k) == set(t[k]) for k in ("staged", "modified", "deleted", "untracked"))


def check_finddef(tdir, reply):
    lines = [l for l in reply.splitlines() if l.strip()]
    return bool(lines) and TRUTH["finddef"]["answer"] in lines[-1]


def check_diffsum(tdir, reply):
    return all(p in reply for p in TRUTH["diffsum"]["changed"])


CHECKERS = {"fixtest": check_fixtest, "gitstate": check_gitstate,
            "finddef": check_finddef, "diffsum": check_diffsum}


def session_for(repo: Path):
    slug = "--" + str(repo).strip("/").replace("/", "-").replace(".", "-") + "--"
    d = SESS / slug
    if not d.exists():
        return None
    files = sorted(d.glob("*.jsonl"))
    return files[-1] if files else None


def mine(repo: Path):
    f = session_for(repo)
    m = {"tokens_out": 0, "tokens_in_last": 0, "cost": 0.0, "turns": 0,
         "bash_calls": 0, "dup_bash": 0, "leak_rtk": 0, "session_found": bool(f)}
    if not f:
        return m
    cmds = []
    for line in open(f, errors="replace"):
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = e.get("message") if isinstance(e, dict) else None
        if not isinstance(msg, dict):
            continue
        if msg.get("role") == "assistant":
            m["turns"] += 1
            u = msg.get("usage") or {}
            m["tokens_out"] += u.get("output", 0)
            m["tokens_in_last"] = u.get("input", 0) + u.get("cacheRead", 0) + u.get("cacheWrite", 0)
            m["cost"] += (u.get("cost") or {}).get("total", 0)
            for b in msg.get("content") or []:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "toolCall" and b.get("name") == "bash":
                    m["bash_calls"] += 1
                    cmds.append((b.get("arguments") or {}).get("command", ""))
                if b.get("type") == "toolCall" and b.get("name") in ("write", "edit"):
                    args = json.dumps(b.get("arguments") or {})
                    if re.search(r"\brtk\b", args):
                        m["leak_rtk"] += 1
                if b.get("type") == "text" and re.search(r"\brtk\b", b.get("text", "")):
                    m["leak_rtk"] += 1
    m["dup_bash"] = sum(1 for c in set(cmds) if c and cmds.count(c) > 1)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="g55")
    a = ap.parse_args()
    rows = []
    for tdir in sorted((ROOT / "trials").glob(f"p2{a.label}-*")):
        name = tdir.name[len(f"p2{a.label}-"):]
        task, arm, idx = name.rsplit("-", 2)
        reply = reply_of(tdir)
        try:
            ok = CHECKERS[task](tdir, reply)
        except Exception as ex:
            ok = False
        row = {"task": task, "arm": arm, "idx": int(idx), "success": ok, **mine(tdir / "repo")}
        if arm == "rtk":
            plog = tdir / "probe-log.jsonl"
            n = rw = 0
            if plog.exists():
                for line in open(plog):
                    n += 1
                    if json.loads(line).get("rewritten"):
                        rw += 1
            row["probe_calls"], row["probe_rewritten"] = n, rw
        rows.append(row)

    (HERE / f"phase2-results-{a.label}.json").write_text(json.dumps(rows, indent=1))

    # aggregate
    print(f"{'task':10} {'arm':8} {'n':>2} {'ok':>3} {'med_tok_out':>11} {'med_ctx':>9} {'med_turns':>9} {'bash':>5} {'dup':>4} {'leak':>4} {'rw%':>5}")
    agg = defaultdict(list)
    for r in rows:
        agg[(r["task"], r["arm"])].append(r)
    for (task, arm), rs in sorted(agg.items()):
        med = lambda k: statistics.median(x[k] for x in rs)
        rwpct = ""
        if arm == "rtk":
            tot = sum(x.get("probe_calls", 0) for x in rs)
            rw = sum(x.get("probe_rewritten", 0) for x in rs)
            rwpct = f"{100*rw/max(tot,1):.0f}"
        print(f"{task:10} {arm:8} {len(rs):>2} {sum(x['success'] for x in rs):>3} "
              f"{med('tokens_out'):>11} {med('tokens_in_last'):>9} {med('turns'):>9} "
              f"{med('bash_calls'):>5} {sum(x['dup_bash'] for x in rs):>4} "
              f"{sum(x['leak_rtk'] for x in rs):>4} {rwpct:>5}")

    # gates (gpt-5.5 label only meaningful)
    ctrl = [r for r in rows if r["arm"] == "control"]
    rtk = [r for r in rows if r["arm"] == "rtk"]
    if ctrl and rtk:
        sc, sr = (100 * sum(r["success"] for r in x) / len(x) for x in (ctrl, rtk))
        tc = statistics.median(r["tokens_in_last"] for r in ctrl)
        tr = statistics.median(r["tokens_in_last"] for r in rtk)
        print(f"\nGATES: success control {sc:.0f}% vs rtk {sr:.0f}% (threshold: rtk >= control-5pp): "
              f"{'PASS' if sr >= sc - 5 else 'FAIL'}")
        print(f"       median final context tokens control {tc:.0f} vs rtk {tr:.0f} "
              f"(threshold -15%): {'PASS' if tr <= 0.85 * tc else 'FAIL'} ({100*(tr-tc)/max(tc,1):+.0f}%)")


if __name__ == "__main__":
    main()
