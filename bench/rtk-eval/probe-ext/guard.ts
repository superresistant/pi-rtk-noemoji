/**
 * Guarded rtk rewrite — single source of truth for Phase 1 re-run and the
 * Phase 2 probe extension.
 *
 * Rule: rewrite a bash command via `rtk rewrite` ONLY if the rtk-wrapped
 * output is consumed by the model (directly or through display-only filters
 * head/tail/cat/less/more). If any machine consumes it — pipe into a
 * computation command, stdout redirect to a file, command substitution —
 * leave the command untouched. Rationale: Phase 1 proved rtk git/ls output
 * is format-unstable under pipes (bench/rtk-eval/PHASE1-RESULTS.md); this
 * rule makes the whole failure class unreachable regardless of which
 * subcommands are affected in any given rtk version.
 *
 * CLI: node --experimental-strip-types guard.ts <rtkBin> <command...>
 *      prints the final command (rewritten or original).
 */
import { spawnSync } from "node:child_process";

const DISPLAY = new Set(["head", "tail", "cat", "less", "more"]);

export function rtkRewrite(rtkBin: string, command: string, homeDir?: string): string | null {
	const res = spawnSync(rtkBin, ["rewrite", command], {
		encoding: "utf-8",
		timeout: 5000,
		env: homeDir ? { ...process.env, HOME: homeDir } : process.env,
	});
	const out = (res.stdout || "").trim();
	if (!out || out === command) return null;
	return out;
}

/** true if every consumer downstream of the rtk invocation is display-only */
function segmentSafe(segment: string): boolean {
	const m = segment.match(/(?:^|\s)rtk\s/);
	if (!m) return true; // no rtk in this segment
	let after = segment.slice((m.index ?? 0) + m[0].length);

	// stderr-only redirects are fine; strip them before inspecting
	after = after.replace(/2>&1|2>>?\s*\S+/g, "");

	// stdout redirect to a file: a machine consumes it later
	if (/(?:^|[^>])>{1,2}\s*\S/.test(after)) return false;

	// pipe chain: every stage must be display-only
	const stages = after.split(/(?<!\|)\|(?!\|)/).slice(1);
	for (const stage of stages) {
		const tok = stage.trim().split(/\s+/)[0] ?? "";
		if (!DISPLAY.has(tok)) return false;
	}
	return true;
}

/** decision only: given the original and its rtk rewrite, keep the rewrite? */
export function wouldKeep(command: string, rewritten: string): boolean {
	// command substitution / backticks: output feeds the shell, not the model
	if (command.includes("$(") || command.includes("`")) return false;
	const segments = rewritten.split(/&&|\|\||;|\n/);
	return segments.every(segmentSafe);
}

export function guardedRewrite(rtkBin: string, command: string, homeDir?: string): string {
	const rewritten = rtkRewrite(rtkBin, command, homeDir);
	if (rewritten === null) return command;
	return wouldKeep(command, rewritten) ? rewritten : command;
}

// CLI mode
if (process.argv[1] && import.meta.url.endsWith(process.argv[1].split("/").pop() ?? "")) {
	const [rtkBin, ...rest] = process.argv.slice(2);
	if (!rtkBin || rest.length === 0) {
		console.error("usage: guard.ts <rtkBin> <command...>");
		process.exit(2);
	}
	process.stdout.write(guardedRewrite(rtkBin, rest.join(" "), process.env.GUARD_HOME));
}
