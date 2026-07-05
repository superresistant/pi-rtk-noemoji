#!/usr/bin/env python3
"""Phase 2 trial runner. Paired A/B: control vs rtk (guarded probe extension).

Usage: python3 run-trials.py --tasks fixtest,gitstate,finddef,diffsum \
          --pairs 8 --model openai-codex/gpt-5.5 [--concurrency 4] [--label g55]

Each trial: fresh byte-identical copy of the task template; rtk arm adds
.pi/extensions/rtk-probe + env. Sessions run in tmux, recorded under the
shared isolated agent dir /tmp/rtk-phase2/agent.
"""
import argparse
import shutil
import subprocess
import time
from pathlib import Path

ROOT = Path("/tmp/rtk-phase2")
EVAL = Path(__file__).resolve().parent.parent  # bench/rtk-eval
PROBE = EVAL / "probe-ext"
RTK = EVAL / "bin/rtk"
AGENT = ROOT / "agent"
TRIALS = ROOT / "trials"
TIMEOUT = 480  # per-session seconds (timeout cmd); tmux killed at +60


def setup_agent():
    if not AGENT.exists():
        AGENT.mkdir(parents=True)
        home_agent = Path.home() / ".pi/agent"
        shutil.copy(home_agent / "auth.json", AGENT / "auth.json")
        shutil.copy(home_agent / "models.json", AGENT / "models.json")
        (AGENT / "settings.json").write_text('{"packages":[]}\n')
    (ROOT / "rtkhome").mkdir(exist_ok=True)


def tmux(*args):
    return subprocess.run(["tmux", *args], capture_output=True, text=True)


def spawn(task: str, arm: str, idx: int, model: str, label: str) -> str:
    name = f"p2{label}-{task}-{arm}-{idx}"
    tdir = TRIALS / name
    if tdir.exists():
        shutil.rmtree(tdir)
    tdir.mkdir(parents=True)
    subprocess.run(["cp", "-a", str(ROOT / "templates" / task / "repo"), str(tdir / "repo")],
                   check=True)
    envs = f"PI_CODING_AGENT_DIR={AGENT}"
    if arm == "rtk":
        ext = tdir / "repo/.pi/extensions/rtk-probe"
        ext.mkdir(parents=True)
        shutil.copy(PROBE / "index.ts", ext / "index.ts")
        shutil.copy(PROBE / "guard.ts", ext / "guard.ts")
        envs += (f" RTK_PROBE_BIN={RTK} RTK_PROBE_HOME={ROOT}/rtkhome"
                 f" RTK_PROBE_LOG={tdir}/probe-log.jsonl")
    cmd = (f"cd {tdir}/repo && {envs} timeout {TIMEOUT} pi -a --model {model} "
           f"-p @{ROOT}/tasks/{task}.md > {tdir}/out.log 2> {tdir}/err.log; "
           f"echo EXIT_CODE=$? >> {tdir}/err.log")
    tmux("new-session", "-d", "-s", name, f"bash -c '{cmd}'")
    return name


def alive(names):
    out = tmux("ls").stdout
    live = {l.split(":")[0] for l in out.splitlines()}
    return [n for n in names if n in live]


def wait_batch(names):
    deadline = time.time() + TIMEOUT + 60
    while time.time() < deadline:
        rest = alive(names)
        if not rest:
            return
        time.sleep(10)
    for n in alive(names):
        tmux("kill-session", "-t", n)
        print(f"  killed stuck {n}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", required=True)
    ap.add_argument("--pairs", type=int, default=8)
    ap.add_argument("--model", default="openai-codex/gpt-5.5")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--label", default="g55")
    ap.add_argument("--start", type=int, default=0, help="first pair index")
    a = ap.parse_args()

    setup_agent()
    TRIALS.mkdir(exist_ok=True)
    jobs = [(task, arm, i)
            for task in a.tasks.split(",")
            for i in range(a.start, a.start + a.pairs)
            for arm in ("control", "rtk")]
    print(f"{len(jobs)} trials, concurrency {a.concurrency}")
    batch = []
    for j, (task, arm, i) in enumerate(jobs):
        batch.append(spawn(task, arm, i, a.model, a.label))
        if len(batch) >= a.concurrency or j == len(jobs) - 1:
            print(f"  batch: {batch}")
            wait_batch(batch)
            batch = []
    print("all trials done")


if __name__ == "__main__":
    main()
