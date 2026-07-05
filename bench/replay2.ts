/**
 * Replay real read-tool results (bench/corpus/read-source.jsonl from survey.py)
 * through sourceCodeFiltering (filterMinimal) + smartTruncation, exactly as
 * index.ts wires them. Run:
 *   node --experimental-strip-types bench/replay2.ts
 */
import * as fs from "node:fs";
import * as path from "node:path";
import * as readline from "node:readline";

import { detectLanguage, filterSourceCode, smartTruncate } from "../techniques/source.ts";

const CORPUS = path.join(import.meta.dirname, "corpus");
const MAX_LINES = 200; // smartTruncation default
const SAMPLE_N = 150;

interface Agg {
	n: number;
	altered: number;
	origChars: number;
	filtChars: number;
	afterSmartChars: number;
	smartApplied: number;
	urlLoss: number; // entries losing "://" occurrences to comment stripping
	urlLossOcc: number;
	hashLoss: number; // python entries losing '#' occurrences
	sampleOrig: string[];
	sampleFilt: string[];
	review: string[];
}

const agg: Agg = { n: 0, altered: 0, origChars: 0, filtChars: 0, afterSmartChars: 0, smartApplied: 0, urlLoss: 0, urlLossOcc: 0, hashLoss: 0, sampleOrig: [], sampleFilt: [], review: [] };

function count(s: string, needle: string): number {
	let c = 0, i = 0;
	while ((i = s.indexOf(needle, i)) !== -1) { c++; i += needle.length; }
	return c;
}

const rl = readline.createInterface({ input: fs.createReadStream(path.join(CORPUS, "read-source.jsonl")) });

rl.on("line", (line) => {
	if (!line.trim()) return;
	const e = JSON.parse(line) as { path: string; output: string; session: string };
	const lang = detectLanguage(e.path);
	if (lang === "unknown") return;
	agg.n++;
	agg.origChars += e.output.length;

	const filt = filterSourceCode(e.output, lang, "minimal");
	agg.filtChars += filt.length;

	let final = filt;
	if (filt.split("\n").length > MAX_LINES) {
		final = smartTruncate(filt, MAX_LINES, lang);
		agg.smartApplied++;
	}
	agg.afterSmartChars += final.length;

	if (filt !== e.output) {
		agg.altered++;
		const urlBefore = count(e.output, "://");
		const urlAfter = count(filt, "://");
		if (urlAfter < urlBefore) {
			agg.urlLoss++;
			agg.urlLossOcc += urlBefore - urlAfter;
			if (agg.review.length < 30) {
				// capture one mangled URL line for review
				const lost = e.output.split("\n").find((l) => l.includes("://") && !filt.includes(l.trim()));
				agg.review.push(JSON.stringify({ path: e.path, session: e.session, lostLine: lost?.slice(0, 160) }));
			}
		}
		if (lang === "python" && count(filt, "#") < count(e.output, "#") - 0) {
			// '#' losses beyond full-line comments are approximated in review only
		}
		if (agg.sampleOrig.length < SAMPLE_N) {
			agg.sampleOrig.push(e.output);
			agg.sampleFilt.push(final);
		}
	}
});

rl.on("close", () => {
	fs.writeFileSync(path.join(CORPUS, "sample-source-orig.txt"), agg.sampleOrig.join("\n"));
	fs.writeFileSync(path.join(CORPUS, "sample-source-filt.txt"), agg.sampleFilt.join("\n"));
	fs.writeFileSync(path.join(CORPUS, "review-source.jsonl"), agg.review.join("\n"));

	const pctMin = (100 * (agg.origChars - agg.filtChars)) / Math.max(agg.origChars, 1);
	const pctAll = (100 * (agg.origChars - agg.afterSmartChars)) / Math.max(agg.origChars, 1);
	console.log(`source-language reads replayed: ${agg.n}`);
	console.log(`altered by filterMinimal: ${agg.altered} (${((100 * agg.altered) / Math.max(agg.n, 1)).toFixed(1)}%)  <- every one of these breaks edit exact-match`);
	console.log(`chars: ${agg.origChars.toLocaleString()} -> minimal ${agg.filtChars.toLocaleString()} (${pctMin.toFixed(1)}%) -> +smartTruncate ${agg.afterSmartChars.toLocaleString()} (${pctAll.toFixed(1)}%)`);
	console.log(`smartTruncate applied (>${MAX_LINES} lines): ${agg.smartApplied}`);
	console.log(`entries losing URL text ("://" chopped as comment): ${agg.urlLoss} (${agg.urlLossOcc} occurrences)`);
});
