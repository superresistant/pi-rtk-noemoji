/**
 * Replay real session bash outputs (bench/corpus/*.jsonl from extract.py)
 * through the actual technique implementations. Reports savings and
 * safety-invariant violations. Run:
 *   node --experimental-strip-types bench/replay.ts
 */
import * as fs from "node:fs";
import * as path from "node:path";

import { aggregateTestOutput } from "../techniques/test-output.ts";
import { filterBuildOutput } from "../techniques/build.ts";
import { aggregateLinterOutput } from "../techniques/linter.ts";
import { compactGitOutput } from "../techniques/git.ts";

const CORPUS = path.join(import.meta.dirname, "corpus");
const SAMPLE_N = 200; // pairs concatenated for ttok token measurement
const REVIEW_N = 30; // before/after pairs for manual review

interface Entry {
	command: string;
	output: string;
	session: string;
	ts: string;
}

// deterministic PRNG for reproducible samples
function mulberry32(seed: number) {
	return () => {
		seed |= 0;
		seed = (seed + 0x6d2b79f5) | 0;
		let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
		t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
		return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
	};
}

function loadCorpus(name: string): Entry[] {
	const file = path.join(CORPUS, `${name}.jsonl`);
	if (!fs.existsSync(file)) return [];
	return fs
		.readFileSync(file, "utf-8")
		.split("\n")
		.filter((l) => l.trim())
		.map((l) => JSON.parse(l));
}

const ERROR_LINE = /^(error\[|error:|\[ERROR\]|FAIL)/m;
const TEST_FAIL_SIGNAL = /(^|\n)\s*(FAIL|FAILED|✕|●)\s|panicked|\d+\s*failed/;

interface CatStats {
	n: number;
	applied: number; // filter returned non-null and changed text
	origChars: number;
	filtChars: number;
	negativeSavings: number; // filtered longer than original
	violations: string[]; // descriptions
}

function run(
	name: string,
	entries: Entry[],
	apply: (out: string, cmd: string) => string | null,
	checkInvariant: (orig: string, filt: string) => string | null
) {
	const s: CatStats = { n: entries.length, applied: 0, origChars: 0, filtChars: 0, negativeSavings: 0, violations: [] };
	const results: { e: Entry; filt: string }[] = [];

	for (const e of entries) {
		const filt = apply(e.output, e.command);
		if (filt === null || filt === e.output) continue;
		s.applied++;
		s.origChars += e.output.length;
		s.filtChars += filt.length;
		if (filt.length > e.output.length) s.negativeSavings++;
		const v = checkInvariant(e.output, filt);
		if (v) s.violations.push(`${v} | cmd: ${e.command.slice(0, 80)} | session: ${e.session}`);
		results.push({ e, filt });
	}

	// samples for token measurement + manual review (Fisher-Yates, seeded)
	const rand = mulberry32(42);
	const shuffled = [...results];
	for (let i = shuffled.length - 1; i > 0; i--) {
		const j = Math.floor(rand() * (i + 1));
		[shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
	}
	const sample = shuffled.slice(0, SAMPLE_N);
	fs.writeFileSync(path.join(CORPUS, `sample-${name}-orig.txt`), sample.map((r) => r.e.output).join("\n"));
	fs.writeFileSync(path.join(CORPUS, `sample-${name}-filt.txt`), sample.map((r) => r.filt).join("\n"));
	fs.writeFileSync(
		path.join(CORPUS, `review-${name}.jsonl`),
		shuffled
			.slice(0, REVIEW_N)
			.map((r) => JSON.stringify({ command: r.e.command, session: r.e.session, before: r.e.output, after: r.filt }))
			.join("\n")
	);

	const pct = s.origChars > 0 ? (100 * (s.origChars - s.filtChars)) / s.origChars : 0;
	console.log(`\n=== ${name} ===`);
	console.log(`entries: ${s.n}, filter applied: ${s.applied} (${((100 * s.applied) / Math.max(s.n, 1)).toFixed(1)}%)`);
	console.log(`chars: ${s.origChars.toLocaleString()} -> ${s.filtChars.toLocaleString()} (${pct.toFixed(1)}% saved on applied calls)`);
	console.log(`filtered longer than original: ${s.negativeSavings}`);
	console.log(`invariant violations: ${s.violations.length}`);
	for (const v of s.violations.slice(0, 8)) console.log(`  VIOLATION: ${v}`);
	if (s.violations.length > 8) console.log(`  ... and ${s.violations.length - 8} more`);
}

// test: a failure signal in the original must survive filtering
run("test", loadCorpus("test"), aggregateTestOutput, (orig, filt) => {
	if (TEST_FAIL_SIGNAL.test(orig) && !/FAIL/.test(filt)) return "failure signal lost";
	return null;
});

// build: error lines in the original must surface as [ERROR]; flag info-destroying success summaries
run("build", loadCorpus("build"), filterBuildOutput, (orig, filt) => {
	if (ERROR_LINE.test(orig) && !filt.includes("[ERROR]")) return "error lines lost";
	return null;
});

run("linter", loadCorpus("linter"), aggregateLinterOutput, (orig, filt) => {
	if (/error/i.test(orig) && /No issues found/.test(filt)) return "errors reported as clean";
	return null;
});

for (const sub of ["git-status", "git-diff", "git-log"]) {
	run(sub, loadCorpus(sub), compactGitOutput, (orig, filt) => {
		if (sub === "git-status" && /^UU /m.test(orig) && !/Conflicts/.test(filt)) return "conflicts lost";
		return null;
	});
}
