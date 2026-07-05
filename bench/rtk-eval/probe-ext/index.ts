/**
 * rtk-probe: Phase 2 probe extension. Rewrites bash commands to rtk
 * equivalents via the guarded rule in guard.ts, before execution.
 *
 * Configuration via environment:
 *   RTK_PROBE_BIN  - absolute path to the pinned rtk binary (required;
 *                    extension is inert without it)
 *   RTK_PROBE_HOME - HOME for rtk state (defaults to process HOME)
 *   RTK_PROBE_LOG  - decision log path (default .rtk-probe-log.jsonl in cwd;
 *                    Phase 2 fixtures MUST set it outside the repo worktree,
 *                    otherwise the log file pollutes git status output)
 */
import * as fs from "node:fs";
import * as path from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { isToolCallEventType } from "@earendil-works/pi-coding-agent";

import { guardedRewrite } from "./guard";

export default function (pi: ExtensionAPI) {
	const rtkBin = process.env.RTK_PROBE_BIN;
	const rtkHome = process.env.RTK_PROBE_HOME;

	pi.on("tool_call", async (event, ctx) => {
		if (!rtkBin) return;
		if (!isToolCallEventType("bash", event)) return;
		const original = event.input.command;
		if (typeof original !== "string" || original.length === 0) return;

		let final = original;
		try {
			final = guardedRewrite(rtkBin, original, rtkHome);
		} catch {
			final = original; // any guard failure -> raw command
		}

		try {
			fs.appendFileSync(
				process.env.RTK_PROBE_LOG || path.join(ctx.cwd || process.cwd(), ".rtk-probe-log.jsonl"),
				JSON.stringify({
					ts: new Date().toISOString(),
					original,
					final,
					rewritten: final !== original,
				}) + "\n"
			);
		} catch {
			// logging must never break the session
		}

		if (final !== original) {
			// Make the pinned binary resolvable inside the bash tool and keep rtk's
			// state (tee logs, gain stats) out of the real home. Execution-only:
			// the model still sees its original command.
			const rtkDir = JSON.stringify(path.dirname(rtkBin));
			const xdg = rtkHome ? ` XDG_DATA_HOME=${JSON.stringify(rtkHome + "/.data")}` : "";
			event.input.command = `export PATH=${rtkDir}:"$PATH"${xdg}\n${final}`;
		}
	});
}
