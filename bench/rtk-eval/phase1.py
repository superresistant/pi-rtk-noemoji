#!/usr/bin/env python3
"""Phase 1: seeded-fact fixtures — do-no-harm gate for rtk.

Builds fixtures under /tmp/rtk-phase1/, runs each command raw and via its
actual `rtk rewrite` mapping (rtk resolved through a private bin dir, isolated
HOME), and checks:
  - planted facts survive rtk rendering (failure signals are gating)
  - pipe-consumer outputs are byte-identical to raw (gating)
  - mutating git commands produce identical repo state (gating)
  - token counts raw vs rtk (ttok) for the record

Run: python3 phase1.py [--skip-npm] [--guarded]
  --guarded routes rewrites through probe-ext/guard.ts (the Phase 2 rule:
  no rewrite when a machine consumes the output). Expected: 28/28 gates.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
RTK = HERE / "bin/rtk"
ISOHOME = Path("/tmp/rtk-phase1/home")
ROOT = Path("/tmp/rtk-phase1")
RTKBIN = ROOT / "rtkbin"

BASE_PATH = f"{Path.home()}/.pi/agent/bin:/usr/local/bin:/usr/bin:/bin"
results = []  # (gate, name, ok, detail)
tokens = []   # (name, raw_tokens, rtk_tokens)


def env_for(rtk_side: bool):
    e = {
        "HOME": str(ISOHOME),
        "PATH": (f"{RTKBIN}:" if rtk_side else "") + BASE_PATH,
        "npm_config_cache": str(Path.home() / ".npm"),
        "TERM": "dumb",
        "GIT_TERMINAL_PROMPT": "0",
    }
    return e


def run(cmd: str, cwd: Path, rtk_side: bool, timeout=120):
    p = subprocess.run(["bash", "-c", cmd], cwd=cwd, env=env_for(rtk_side),
                       capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout + p.stderr


GUARDED = "--guarded" in sys.argv
GUARD = HERE / "probe-ext/guard.ts"


def rewrite(cmd: str) -> str:
    if GUARDED:
        e = env_for(False)
        e["GUARD_HOME"] = str(ISOHOME)
        p = subprocess.run(["node", "--experimental-strip-types", str(GUARD), str(RTK), cmd],
                           capture_output=True, text=True, env={**os.environ, **e}, timeout=20)
        out = p.stdout.strip()
        return out if out else cmd
    p = subprocess.run([str(RTK), "rewrite", cmd], capture_output=True, text=True,
                       env=env_for(False), timeout=10)
    out = p.stdout.strip()
    return out if out else cmd


def ttok(text: str) -> int:
    p = subprocess.run(["ttok"], input=text, capture_output=True, text=True, timeout=60)
    try:
        return int(p.stdout.strip())
    except ValueError:
        return -1


def check(gate: bool, name: str, ok: bool, detail: str = ""):
    results.append((gate, name, ok, detail))
    print(f"  [{'GATE' if gate else 'info'}] {name}: {'PASS' if ok else 'FAIL'} {detail}")


def pair(name: str, cmd: str, cwd: Path, facts=(), gate_facts=(), rtk_facts=(),
         pipe_identity=False, exit_nonzero=False, timeout=120):
    """Run raw vs rewritten; check facts on rtk output, identity for pipes."""
    rw = rewrite(cmd)
    rc_raw, out_raw = run(cmd, cwd, rtk_side=False, timeout=timeout)
    rc_rtk, out_rtk = run(rw, cwd, rtk_side=True, timeout=timeout)
    print(f"\n== {name}\n   raw: {cmd}\n   rtk: {rw}")

    for f in facts:
        present_raw = f in out_raw
        present_rtk = f in out_rtk
        is_gate = f in gate_facts
        if not present_raw:
            check(is_gate, f"{name}: fact '{f}' present in RAW (sanity)", False, "fact not in raw output — fixture bug")
        else:
            check(is_gate, f"{name}: fact '{f}' survives rtk", present_rtk)
    for f in rtk_facts:
        check(True, f"{name}: rtk-format fact '{f}' present", f in out_rtk)

    if pipe_identity:
        check(True, f"{name}: pipe output byte-identical",
              out_raw == out_rtk and rc_raw == rc_rtk,
              "" if out_raw == out_rtk else f"raw={out_raw[:60]!r} rtk={out_rtk[:60]!r}")

    if exit_nonzero:
        check(True, f"{name}: raw exit nonzero (sanity)", rc_raw != 0, f"rc={rc_raw}")
        check(True, f"{name}: rtk exit nonzero", rc_rtk != 0, f"rc={rc_rtk}")

    tokens.append((name, ttok(out_raw), ttok(out_rtk)))
    return out_raw, out_rtk


def sh(cmds: str, cwd: Path):
    subprocess.run(["bash", "-ec", cmds], cwd=cwd, env=env_for(False),
                   capture_output=True, text=True, timeout=300, check=True)


def build_fixtures(skip_npm: bool):
    shutil.rmtree(ROOT, ignore_errors=True)
    ROOT.mkdir(parents=True)
    ISOHOME.mkdir(parents=True)
    RTKBIN.mkdir()
    (RTKBIN / "rtk").symlink_to(RTK)
    (ISOHOME / ".gitconfig").write_text(
        "[user]\n name = Phase1\n email = p1@example.invalid\n[init]\n defaultBranch = main\n")

    # git fixture: staged, modified, untracked, UU conflict, 3-file diff, known log
    g = ROOT / "gitfix"
    g.mkdir()
    sh("""
git init -q -b phase1-branch
for f in staged modified conflict d1 d2 d3; do printf 'line1\\nline2\\nline3\\n' > $f.txt; done
git add -A && git commit -qm commit-alpha-one
git checkout -qb side
printf 'SIDE\\nline2\\nline3\\n' > conflict.txt
git commit -qam commit-beta-two
git checkout -q phase1-branch
printf 'MAIN\\nline2\\nline3\\n' > conflict.txt
git commit -qam commit-gamma-three
git merge side >/dev/null 2>&1 || true
printf 'STAGEDCHANGE\\nline2\\nline3\\n' > staged.txt && git add staged.txt
printf 'MODCHANGE\\nline2\\nline3\\n' > modified.txt
printf 'new\\n' > untracked.txt
printf 'D1CHANGE\\nline2\\nline3\\n' > d1.txt
printf 'line1\\nD2CHANGE\\nline3\\n' > d2.txt
printf 'line1\\nline2\\nD3CHANGE\\n' > d3.txt
""", g)

    # search fixture
    s = ROOT / "searchfix"
    (s / "src").mkdir(parents=True)
    (s / "src/alpha.ts").write_text("const a = 1;\nconst b = 2;\nconst x = 'NEEDLE_ALPHA';\n")
    (s / "src/beta.py").write_text("\n\n\n\n\n\nval = 'NEEDLE_ALPHA'\n")
    (s / "src/gamma.md").write_text("# title\nNEEDLE_ALPHA here\n")
    (s / "data.json").write_text('{"alpha": 42, "items": [1, 2, 3], "name": "phase1"}\n')
    (s / "src/app.ts").write_text(
        "// IMPORTANT_COMMENT_FACT explains the constant\n"
        "const SECRET_VALUE = 12345;\n"
        "const API_URL = \"https://api.example.com/v1\";\n"
        "export function knownFunctionName(x: number): number {\n"
        "\treturn x + SECRET_VALUE;\n"
        "}\n")

    # node fixture: vitest failing tests + tsc type error
    n = ROOT / "nodefix"
    n.mkdir()
    (n / "package.json").write_text('{"name":"p1","private":true,"type":"module"}\n')
    (n / "math.test.ts").write_text(
        "import { describe, it, expect } from 'vitest';\n"
        "describe('phase1', () => {\n"
        "\tit('known_pass_one', () => { expect(1).toBe(1); });\n"
        "\tit('known_fail_alpha', () => { expect(1).toBe(2); });\n"
        "\tit('known_fail_beta', () => { expect('a').toBe('b'); });\n"
        "});\n")
    (n / "app.ts").write_text("export const x: number = 'not-a-number';\n")
    (n / "tsconfig.json").write_text('{"compilerOptions":{"strict":true,"noEmit":true}}\n')
    if not skip_npm:
        sh("npm i -D vitest typescript --no-audit --no-fund --silent", n)

    # mutating twin repos
    for name in ("m-raw", "m-rtk"):
        m = ROOT / name
        m.mkdir()
        sh("git init -q -b main && printf 'base\\n' > f.txt && git add -A && git commit -qm base"
           " && printf 'changed\\n' > f.txt && printf 'brand-new\\n' > g.txt", m)


def main():
    skip_npm = "--skip-npm" in sys.argv
    build_fixtures(skip_npm)
    g, s, n = ROOT / "gitfix", ROOT / "searchfix", ROOT / "nodefix"

    pair("git-status", "git status", g,
         facts=("phase1-branch", "staged.txt", "modified.txt", "untracked.txt", "conflict.txt"),
         gate_facts=("conflict.txt",))
    pair("git-status-porcelain-wc", "git status --porcelain | wc -l", g, pipe_identity=True)
    pair("git-diff", "git diff", g,
         facts=("d1.txt", "d2.txt", "d3.txt", "D1CHANGE", "D2CHANGE", "D3CHANGE"),
         gate_facts=("d1.txt", "d2.txt", "d3.txt"))
    pair("git-log", "git log --oneline -5", g,
         facts=("commit-alpha-one", "commit-gamma-three"))

    pair("rg-n", "rg -n NEEDLE_ALPHA src/", s,
         facts=("alpha.ts", "beta.py", "gamma.md", "3", "7"),
         gate_facts=("alpha.ts", "beta.py", "gamma.md"))
    pair("rg-wc", "rg NEEDLE_ALPHA src/ | wc -l", s, pipe_identity=True)
    pair("rg-l-sort", "rg -l NEEDLE_ALPHA src/ | sort", s, pipe_identity=True)
    pair("grep-rc", "grep -rc NEEDLE_ALPHA src/", s, pipe_identity=True)
    pair("read-json-jq", "cat data.json | jq .alpha", s, pipe_identity=True)
    pair("ls", "ls -la src/", s, facts=("alpha.ts", "beta.py", "gamma.md", "app.ts"))
    pair("read-source", "cat src/app.ts", s,
         facts=("SECRET_VALUE = 12345", "https://api.example.com/v1",
                "knownFunctionName", "IMPORTANT_COMMENT_FACT"),
         gate_facts=("SECRET_VALUE = 12345", "knownFunctionName"))

    if not skip_npm:
        pair("vitest", "npx vitest run 2>&1", n,
             facts=("known_fail_alpha", "known_fail_beta", "2 failed"),
             gate_facts=("known_fail_alpha", "known_fail_beta"),
             rtk_facts=("FAIL (2)",),
             exit_nonzero=True, timeout=180)
        pair("tsc", "npx tsc --noEmit 2>&1", n,
             facts=("app.ts", "TS2322"), gate_facts=("app.ts", "TS2322"),
             exit_nonzero=True, timeout=180)

    # curl against a local server
    srv = subprocess.Popen(["python3", "-m", "http.server", "8971", "--bind", "127.0.0.1"],
                           cwd=s, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        import time
        time.sleep(1.0)
        pair("curl-jq", "curl -s http://127.0.0.1:8971/data.json | jq .alpha", s, pipe_identity=True)
        raw, rtk_out = pair("curl-body", "curl -s http://127.0.0.1:8971/data.json", s)
        check(True, "curl-body: body identical", raw == rtk_out,
              "" if raw == rtk_out else f"raw={raw[:60]!r} rtk={rtk_out[:60]!r}")
    finally:
        srv.terminate()

    # mutating git: identical end state
    print("\n== git-mutate")
    rc1, _ = run("git add -A && git commit -m 'phase1 commit'", ROOT / "m-raw", rtk_side=False)
    rw = rewrite("git add -A && git commit -m 'phase1 commit'")
    rc2, _ = run(rw, ROOT / "m-rtk", rtk_side=True)
    print(f"   rtk: {rw}")
    t1 = run("git rev-parse HEAD^{tree}", ROOT / "m-raw", False)[1].strip()
    t2 = run("git rev-parse HEAD^{tree}", ROOT / "m-rtk", False)[1].strip()
    s1 = run("git status --porcelain", ROOT / "m-raw", False)[1]
    s2 = run("git status --porcelain", ROOT / "m-rtk", False)[1]
    m1 = run("git log -1 --format=%s", ROOT / "m-raw", False)[1].strip()
    m2 = run("git log -1 --format=%s", ROOT / "m-rtk", False)[1].strip()
    check(True, "git-mutate: tree hash identical", t1 == t2 and t1 != "", f"{t1[:12]} vs {t2[:12]}")
    check(True, "git-mutate: worktree clean both", s1 == "" and s2 == "")
    check(True, "git-mutate: commit message identical", m1 == m2 == "phase1 commit")

    # summary
    gates = [r for r in results if r[0]]
    gfail = [r for r in gates if not r[2]]
    info = [r for r in results if not r[0]]
    ifail = [r for r in info if not r[2]]
    print(f"\n=== SUMMARY: gates {len(gates)-len(gfail)}/{len(gates)} passed, "
          f"info {len(info)-len(ifail)}/{len(info)} passed")
    for _, name, _, detail in gfail:
        print(f"  GATE FAIL: {name} {detail}")
    for _, name, _, detail in ifail:
        print(f"  info fail: {name} {detail}")
    print("\ntokens (raw -> rtk):")
    for name, a, b in tokens:
        pct = f"{100*(1-b/a):.0f}%" if a > 0 and b >= 0 else "n/a"
        print(f"  {name:26} {a:>7} -> {b:>7}  ({pct})")
    (HERE / "phase1-raw-results.json").write_text(json.dumps(
        {"results": results, "tokens": tokens}, indent=1))
    sys.exit(1 if gfail else 0)


if __name__ == "__main__":
    main()
