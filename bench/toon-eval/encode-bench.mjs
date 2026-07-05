/**
 * TOON track B: encode real JSON samples (samples/{sweet,mixed}.jsonl from
 * scan.py), measure char savings, verify lossless roundtrip.
 * JSONL inputs are wrapped into an array first (what an agent would do via jq -s).
 * Writes concatenated raw/toon text for ttok. Run: node encode-bench.mjs
 */
import * as fs from "node:fs";
import * as readline from "node:readline";
import { encode, decode } from "@toon-format/toon";

function canon(x) {
	if (Array.isArray(x)) return x.map(canon);
	if (x && typeof x === "object")
		return Object.fromEntries(Object.keys(x).sort().map((k) => [k, canon(x[k])]));
	return x;
}

function parseSample(text) {
	const s = text.trim();
	if (s[0] === "{" || s[0] === "[") {
		try { return JSON.parse(s); } catch { /* fallthrough */ }
	}
	const lines = s.split("\n").filter((l) => l.trim());
	return lines.map((l) => JSON.parse(l)); // jsonl -> array
}

for (const cls of ["sweet", "mixed"]) {
	const rl = readline.createInterface({ input: fs.createReadStream(`samples/${cls}.jsonl`) });
	let n = 0, rawChars = 0, toonChars = 0, rtFail = 0, encFail = 0;
	const rawOut = fs.createWriteStream(`samples/${cls}-raw.txt`);
	const toonOut = fs.createWriteStream(`samples/${cls}-toon.txt`);
	await new Promise((resolve) => {
		rl.on("line", (line) => {
			if (!line.trim()) return;
			const { text } = JSON.parse(line);
			let obj;
			try { obj = parseSample(text); } catch { return; }
			let t;
			try { t = encode(obj); } catch { encFail++; return; }
			n++;
			rawChars += text.length;
			toonChars += t.length;
			try {
				const back = decode(t);
				if (JSON.stringify(canon(back)) !== JSON.stringify(canon(obj))) rtFail++;
			} catch { rtFail++; }
			if (rawChars < 3_000_000) { rawOut.write(text + "\n"); toonOut.write(t + "\n"); }
		});
		rl.on("close", resolve);
	});
	rawOut.end(); toonOut.end();
	const pct = ((100 * (rawChars - toonChars)) / Math.max(rawChars, 1)).toFixed(1);
	console.log(`${cls}: n=${n} encodeFail=${encFail} roundtripFail=${rtFail} chars ${rawChars.toLocaleString()} -> ${toonChars.toLocaleString()} (${pct}% saved)`);
}
