/**
 * Apply the guard decision to the full real-history rewrite mapping
 * (../rewrites.jsonl from phase0b.py) and report kept vs declined coverage.
 * Run: node --experimental-strip-types guard-stats.ts
 */
import * as fs from "node:fs";
import * as path from "node:path";
import * as readline from "node:readline";
import { wouldKeep } from "./guard.ts";

const file = path.resolve(import.meta.dirname, "../rewrites.jsonl");
const rl = readline.createInterface({ input: fs.createReadStream(file) });

let kept = [0, 0];
let declined = [0, 0];

rl.on("line", (line) => {
	if (!line.trim()) return;
	const e = JSON.parse(line) as { c: string; rw: string; calls: number; chars: number };
	const t = wouldKeep(e.c, e.rw) ? kept : declined;
	t[0] += e.calls;
	t[1] += e.chars;
});

rl.on("close", () => {
	const tot = [kept[0] + declined[0], kept[1] + declined[1]];
	const pct = (a: number, b: number) => ((100 * a) / Math.max(b, 1)).toFixed(1);
	console.log(`rewritten calls in history: ${tot[0]}, output chars ${tot[1].toLocaleString()}`);
	console.log(`guard KEEPS:    ${kept[0]} calls (${pct(kept[0], tot[0])}%)  ${kept[1].toLocaleString()} chars (${pct(kept[1], tot[1])}%)`);
	console.log(`guard DECLINES: ${declined[0]} calls (${pct(declined[0], tot[0])}%)  ${declined[1].toLocaleString()} chars (${pct(declined[1], tot[1])}%)`);
	console.log(`net coverage of all bash output (200.1M chars): ${pct(kept[1], 200_117_202)}%`);
});
