/**
 * Guard unit tests against the real pinned binary.
 * Run: RTK_BIN=../bin/rtk node --experimental-strip-types guard-test.ts
 */
import * as path from "node:path";
import { guardedRewrite } from "./guard.ts";

const rtkBin = path.resolve(import.meta.dirname, process.env.RTK_BIN ?? "../bin/rtk");
const home = path.resolve(import.meta.dirname, "../home");

// [command, expectRewritten, why]
const CASES: [string, boolean, string][] = [
	["git status", true, "plain view"],
	["cd /repo && git status", true, "compound view"],
	["git status --porcelain | wc -l", false, "pipe into computation"],
	["git status --short | grep '^.M' | wc -l", false, "pipe chain into computation"],
	["rg foo src/ | head -20", true, "display-only pipe"],
	["rg foo src/ | head -20 | wc -l", false, "display then computation"],
	["rg -l foo | xargs sed -i s/a/b/", false, "machine acts on output"],
	["cat data.json | jq .x", false, "jq consumes"],
	["cat notes.md", true, "plain read"],
	["cat notes.md | tail -5", true, "display-only"],
	["git diff > /tmp/out.diff", false, "stdout redirected to file"],
	["git diff 2>&1", true, "stderr merge is not consumption"],
	["git diff 2>/dev/null", true, "stderr drop is not consumption"],
	["echo $(git status --short)", false, "command substitution"],
	["N=`git status --short`", false, "backtick substitution"],
	["ls -la | wc -l", false, "ls counted"],
	["ls -la", true, "ls view"],
	["npx vitest run 2>&1 | tail -20", true, "test run, display pipe"],
	["python3 setup.py --version", false, "no rtk equivalent -> unchanged"],
	["git add -A && git commit -m x && git status --short | wc -l", false,
		"mutating segments fine but counted status segment poisons: expect raw"],
];

let fail = 0;
for (const [cmd, expectRw, why] of CASES) {
	const out = guardedRewrite(rtkBin, cmd, home);
	const rewritten = out !== cmd;
	const ok = rewritten === expectRw;
	if (!ok) fail++;
	console.log(`${ok ? "PASS" : "FAIL"} [${why}] ${cmd}\n     -> ${out}`);
}
console.log(fail === 0 ? "\nALL PASS" : `\n${fail} FAILURES`);
process.exit(fail === 0 ? 0 : 1);
