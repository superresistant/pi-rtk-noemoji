#!/usr/bin/env python3
"""Phase 2 fixture templates + task prompts. Deterministic (seeded).

Creates /tmp/rtk-phase2/{templates/<task>/repo, tasks/<task>.md, truth.json}.
Each trial later copies a template byte-identically (cp -a).
Tasks: fixtest, gitstate, finddef, diffsum.
"""
import json
import random
import shutil
import subprocess
from pathlib import Path

ROOT = Path("/tmp/rtk-phase2")
T = ROOT / "templates"
TASKS = ROOT / "tasks"
random.seed(1234)

GITENV = {"HOME": str(ROOT / "githome"), "PATH": "/usr/local/bin:/usr/bin:/bin",
          "npm_config_cache": str(Path.home() / ".npm")}


def sh(cmds, cwd):
    subprocess.run(["bash", "-ec", cmds], cwd=cwd, env=GITENV, check=True,
                   capture_output=True, timeout=600)


def filler_ts(name, n=40):
    lines = [f"// module {name}", f"export const {name}_VERSION = {random.randint(1,99)};"]
    for i in range(n):
        a, b = random.randint(1, 9), random.randint(1, 9)
        lines.append(f"export function {name}_util{i}(x: number): number {{ return x * {a} + {b}; }}")
    return "\n".join(lines) + "\n"


def repo_init(d):
    sh("git init -q -b main && printf '.pi/\\nnode_modules/\\n' > .gitignore", d)


def commit_all(d, msg):
    sh(f"git add -A && git commit -qm '{msg}'", d)


def make_fixtest():
    d = T / "fixtest/repo"
    (d / "src").mkdir(parents=True)
    (d / "tests").mkdir()
    repo_init(d)
    (d / "package.json").write_text('{"name":"fixtest","private":true,"type":"module"}\n')
    (d / "src/pricing.ts").write_text(
        "export function applyDiscount(price: number, pct: number): number {\n"
        "\t// apply a percentage discount to a price\n"
        "\treturn price * (1 + pct / 100);\n"
        "}\n"
        "export function addTax(price: number, pct: number): number {\n"
        "\treturn price * (1 + pct / 100);\n"
        "}\n")
    for m in ("inventory", "shipping", "labels"):
        (d / f"src/{m}.ts").write_text(filler_ts(m, 25))
    (d / "tests/pricing.test.ts").write_text(
        "import { it, expect } from 'vitest';\n"
        "import { applyDiscount, addTax } from '../src/pricing.ts';\n"
        "it('discount_20_pct_off_100', () => { expect(applyDiscount(100, 20)).toBe(80); });\n"
        "it('discount_50_pct_off_40', () => { expect(applyDiscount(40, 50)).toBe(20); });\n"
        "it('tax_10_pct_on_100', () => { expect(addTax(100, 10)).toBeCloseTo(110); });\n")
    (d / "tests/inventory.test.ts").write_text(
        "import { it, expect } from 'vitest';\n"
        "import * as inv from '../src/inventory.ts';\n" +
        "".join(f"it('inv_util{i}', () => {{ expect(typeof inv.inventory_util{i}(2)).toBe('number'); }});\n"
                for i in range(12)))
    sh("npm i -D vitest typescript --no-audit --no-fund --silent", d)
    commit_all(d, "base")
    return {"failing": ["discount_20_pct_off_100", "discount_50_pct_off_40"],
            "test_files": ["tests/pricing.test.ts", "tests/inventory.test.ts"]}


def make_gitstate():
    d = T / "gitstate/repo"
    (d / "src").mkdir(parents=True)
    repo_init(d)
    for i in range(24):
        (d / f"src/mod{i:02}.ts").write_text(filler_ts(f"mod{i:02}", 15))
    (d / "README.md").write_text("# gitstate fixture\n")
    commit_all(d, "base")
    sh("""
printf 'STAGEDX\\n' >> src/mod01.ts && printf 'STAGEDY\\n' >> src/mod07.ts
git add src/mod01.ts src/mod07.ts
printf 'MODA\\n' >> src/mod03.ts && printf 'MODB\\n' >> src/mod11.ts && printf 'MODC\\n' >> src/mod19.ts
rm src/mod22.ts
printf 'new\\n' > src/newfile_a.ts && printf 'new\\n' > notes_b.md
""", d)
    return {"staged": ["src/mod01.ts", "src/mod07.ts"],
            "modified": ["src/mod03.ts", "src/mod11.ts", "src/mod19.ts"],
            "deleted": ["src/mod22.ts"],
            "untracked": ["src/newfile_a.ts", "notes_b.md"]}


def make_finddef():
    d = T / "finddef/repo"
    d.mkdir(parents=True)
    repo_init(d)
    dirs = ["src/api", "src/pricing/deep", "src/ui", "src/lib", "src/jobs", "docs"]
    for dd in dirs:
        (d / dd).mkdir(parents=True)
    for i in range(45):
        (d / dirs[i % 5] / f"file{i:02}.ts").write_text(filler_ts(f"f{i:02}", 20))
    (d / "src/pricing/deep/base.ts").write_text(
        "import { f00_util0 } from '../../api/file00.ts';\n"
        "export function computeTariffBase(zone: number, weight: number): number {\n"
        "\treturn f00_util0(zone) + weight * 3;\n"
        "}\n")
    # decoys: imports/usages elsewhere
    for i, dd in enumerate(["src/api", "src/ui", "src/lib", "src/jobs"]):
        (d / dd / f"uses{i}.ts").write_text(
            "import { computeTariffBase } from '../pricing/deep/base.ts';\n"
            f"export const r{i} = computeTariffBase({i}, {i + 1});\n")
    (d / "docs/notes.md").write_text("computeTariffBase is the core tariff entry point.\n")
    commit_all(d, "base")
    return {"answer": "src/pricing/deep/base.ts"}


def make_diffsum():
    d = T / "diffsum/repo"
    (d / "src").mkdir(parents=True)
    repo_init(d)
    for i in range(20):
        (d / f"src/part{i:02}.ts").write_text(filler_ts(f"part{i:02}", 30))
    commit_all(d, "base")
    # three working changes with distinct signatures
    a = d / "src/part03.ts"
    a.write_text(a.read_text().replace("* 3 +", "* 30 +") +
                 "".join(f"export function part03_extra{i}(x: number) {{ return x - {i}; }}\n"
                         for i in range(15)))
    b = d / "src/part09.ts"
    b.write_text(b.read_text() +
                 "\nexport class RetryQueue {\n\tprivate items: number[] = [];\n"
                 "\tpush(x: number) { this.items.push(x); }\n"
                 "\tdrain(): number { return this.items.length; }\n}\n")
    c = d / "src/part14.ts"
    lines = c.read_text().split("\n")
    c.write_text("\n".join(lines[:8]) + "\n")  # mass deletion
    return {"changed": ["src/part03.ts", "src/part09.ts", "src/part14.ts"]}


PROMPTS = {
    "fixtest": "The test suite in this repo has failures. Run it, find the bug, fix it so the whole suite passes. Do not modify any file under tests/. When the suite is green, reply with the single word: DONE",
    "gitstate": "Inspect the git working tree of this repo and report its exact state. Reply with exactly four lines and nothing else:\nstaged: <comma-separated paths>\nmodified: <comma-separated paths>\ndeleted: <comma-separated paths>\nuntracked: <comma-separated paths>\nUse paths relative to the repo root. Ignore anything covered by .gitignore.",
    "finddef": "In which file is the function computeTariffBase DEFINED (not imported or called)? Reply with the relative path only, nothing else.",
    "diffsum": "This repo has uncommitted changes. Summarize them: reply with exactly one line per changed file in the form '<path>: <short description of the change>' and nothing else.",
}


def main():
    shutil.rmtree(ROOT, ignore_errors=True)
    (ROOT / "githome").mkdir(parents=True)
    (ROOT / "githome/.gitconfig").write_text(
        "[user]\n name = P2\n email = p2@example.invalid\n[init]\n defaultBranch = main\n")
    TASKS.mkdir(parents=True)
    truth = {}
    for name, fn in (("fixtest", make_fixtest), ("gitstate", make_gitstate),
                     ("finddef", make_finddef), ("diffsum", make_diffsum)):
        (T / name).mkdir(parents=True)
        truth[name] = fn()
        (TASKS / f"{name}.md").write_text(PROMPTS[name] + "\n")
        print(f"template {name} ready")
    (ROOT / "truth.json").write_text(json.dumps(truth, indent=1))


if __name__ == "__main__":
    main()
