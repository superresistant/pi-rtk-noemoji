/**
 * pi-rtk-debunked — the one token-reduction technique that survived
 * measurement: ANSI stripping on bash tool output.
 *
 * Every other technique (test/build/linter/git compaction, source filtering,
 * truncation, search grouping — and, in bench/, pre-execution rewriting and
 * TOON re-encoding) was measured against real session history and removed
 * or rejected. Claims vs proofs: README.md and bench/.
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { isBashToolResult } from "@earendil-works/pi-coding-agent";

import { loadConfig, DEFAULT_CONFIG, type RtkConfig } from "./config";
import { trackSavings, getMetricsSummary, clearMetrics } from "./metrics";
import { stripAnsiFast } from "./techniques";

// Initialize with defaults immediately so tool_result handler works before session_start fires
let config: RtkConfig = DEFAULT_CONFIG;
let enabled = true;
let processedCount = 0;

export default function (pi: ExtensionAPI) {
	let loaded = false;

	pi.on("session_start", async (_event, ctx) => {
		if (loaded) return;
		loaded = true;

		try {
			config = await loadConfig(ctx.cwd || process.cwd());
			enabled = config.enabled;
			if (enabled && ctx.hasUI) {
				ctx.ui.notify("RTK plugin loaded - token reduction active", "info");
			}
		} catch {
			if (ctx.hasUI) {
				ctx.ui.notify("RTK plugin loaded (using defaults)", "info");
			}
		}
	});

	pi.on("tool_result", async (event, _ctx) => {
		if (!enabled) return;
		if (!isBashToolResult(event)) return;
		if (!config.techniques.ansiStripping) return;

		const content = event.content;
		const textItem = content?.find((c) => c.type === "text");
		if (!textItem || !("text" in textItem)) return;

		const originalText = textItem.text;
		const filteredText = stripAnsiFast(originalText);
		if (filteredText === originalText) return;

		trackSavings(originalText, filteredText, "bash", "ansi");
		processedCount++;

		return {
			content: content.map((c) => (c.type === "text" ? { ...c, text: filteredText } : c)),
		};
	});

	pi.registerCommand("rtk-stats", {
		description: "Show RTK output savings statistics (chars)",
		handler: async (_args, ctx) => {
			ctx.ui.notify(getMetricsSummary(), "info");
		},
	});

	pi.registerCommand("rtk-on", {
		description: "Enable RTK token reduction",
		handler: async (_args, ctx) => {
			enabled = true;
			ctx.ui.notify("RTK token reduction enabled", "info");
		},
	});

	pi.registerCommand("rtk-off", {
		description: "Disable RTK token reduction",
		handler: async (_args, ctx) => {
			enabled = false;
			ctx.ui.notify("RTK token reduction disabled", "warning");
		},
	});

	pi.registerCommand("rtk-toggle-ansiStripping", {
		description: "Toggle the ansiStripping technique on/off",
		handler: async (_args, ctx) => {
			config.techniques.ansiStripping = !config.techniques.ansiStripping;
			ctx.ui.notify(
				`RTK ansiStripping ${config.techniques.ansiStripping ? "enabled" : "disabled"}`,
				config.techniques.ansiStripping ? "info" : "warning"
			);
		},
	});

	pi.registerCommand("rtk-clear", {
		description: "Clear RTK metrics history",
		handler: async (_args, ctx) => {
			clearMetrics();
			processedCount = 0;
			ctx.ui.notify("RTK metrics cleared", "info");
		},
	});

	pi.registerCommand("rtk-what", {
		description: "Show current RTK technique configuration",
		handler: async (_args, ctx) => {
			const summary = [
				`RTK enabled: ${enabled}`,
				`ansiStripping: ${config.techniques.ansiStripping}`,
			].join("\n");
			ctx.ui.notify(summary, "info");
		},
	});
}
