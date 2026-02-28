/**
 * RTK (Rust Token Killer) Plugin for Pi-Coding-Agent
 *
 * Reduces token consumption by intelligently filtering tool output.
 * Based on techniques from RTK.md - 60-90% token reduction while preserving essential information.
 */

import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import {
	isBashToolResult,
	isReadToolResult,
	isGrepToolResult,
} from "@mariozechner/pi-coding-agent";

import { loadConfig, DEFAULT_CONFIG, type RtkConfig } from "./config";
import { trackSavings, getMetricsSummary, clearMetrics } from "./metrics";
import {
	stripAnsiFast,
	truncate,
	filterSourceCode,
	detectLanguage,
	filterBuildOutput,
	isBuildCommand,
	aggregateTestOutput,
	isTestCommand,
	aggregateLinterOutput,
	isLinterCommand,
	compactGitOutput,
	isGitCommand,
	groupSearchResults,
	smartTruncate,
} from "./techniques";

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



	pi.on("tool_result", async (event, ctx) => {
		if (!enabled) return;
		let technique = "";

		// ── BASH ──────────────────────────────────────
		if (isBashToolResult(event)) {
			const content = event.content;
			const command = (event.input as { command?: string }).command;

			const textItem = content?.find((c) => c.type === "text");
			if (!textItem || !("text" in textItem)) return;

			const originalText = textItem.text;
			let filteredText = originalText;

			if (config.techniques.ansiStripping) {
				const stripped = stripAnsiFast(filteredText);
				if (stripped !== filteredText) {
			filteredText = stripped;
					technique = technique ? `${technique},ansi` : "ansi";
			}
			}

			if (config.techniques.buildOutputFiltering && isBuildCommand(command)) {
				const out = filterBuildOutput(filteredText, command);
				if (out !== null && out !== filteredText) {
					filteredText = out;
					technique = technique ? `${technique},build` : "build";
				}
			}

			if (config.techniques.testOutputAggregation && isTestCommand(command)) {
				const out = aggregateTestOutput(filteredText, command);
				if (out !== null && out !== filteredText) {
					filteredText = out;
					technique = technique ? `${technique},test` : "test";
				}
			}

			if (config.techniques.gitCompaction && isGitCommand(command)) {
				const out = compactGitOutput(filteredText, command);
		if (out !== null && out !== filteredText) {
					filteredText = out;
					technique = technique ? `${technique},git` : "git";
				}
			}

			if (config.techniques.linterAggregation && isLinterCommand(command)) {
				const out = aggregateLinterOutput(filteredText, command);
				if (out !== null && out !== filteredText) {
					filteredText = out;
					technique = technique ? `${technique},linter` : "linter";
				}
			}

			if (config.techniques.truncation.enabled && filteredText.length > config.techniques.truncation.maxChars) {
				filteredText = truncate(filteredText, config.techniques.truncation.maxChars);
				technique = technique ? `${technique},truncate` : "truncate";
			}

			if (filteredText !== originalText) {
			const record = trackSavings(originalText, filteredText, "bash", technique);
				processedCount++;

	

				return {
					content: content.map((c) =>
						c.type === "text" ? { ...c, text: filteredText } : c
					),
				};
			}
		}

		// ── READ ───────────────────────────────
		if (isReadToolResult(event)) {
			const content = event.content;
			const filePath = (event.input as { path?: string }).path || "";
			const language = detectLanguage(filePath);

			const textItem = content?.find((c) => c.type === "text");
			if (!textItem || !("text" in textItem)) return;

			const originalText = textItem.text;

		if (config.techniques.sourceCodeFiltering.enabled && language !== "unknown") {
				let filteredText = filterSourceCode(originalText, language, config.techniques.sourceCodeFiltering.level);

				if (
					config.techniques.smartTruncation.enabled &&
					filteredText.split("\n").length > config.techniques.smartTruncation.maxLines
			) {
					filteredText = smartTruncate(filteredText, config.techniques.smartTruncation.maxLines, language);
					technique = "source+smart";
				} else {
				technique = "source";
			}

				if (filteredText !== originalText) {
					const record = trackSavings(originalText, filteredText, "read", technique);
					processedCount++;

	

					return {
						content: content.map((c) =>
							c.type === "text" ? { ...c, text: filteredText } : c
						),
					};
				}
			}
		}

		// ── GREP ──────────────────────────
		if (isGrepToolResult(event)) {
			if (!config.techniques.searchResultGrouping) return;

			const content = event.content;
			const textItem = content?.find((c) => c.type === "text");
			if (!textItem || !("text" in textItem)) return;

			const originalText = textItem.text;
			const grouped = groupSearchResults(originalText);

			if (grouped !== null && grouped !== originalText) {
				const record = trackSavings(originalText, grouped, "grep", "search");
				processedCount++;

				return {
					content: content.map((c) =>
					c.type === "text" ? { ...c, text: grouped } : c
					),
				};
			}
		}
	});

	pi.registerCommand("rtk-stats", {
		description: "Show RTK token savings statistics",
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

	const booleanTechniques = [
		"ansiStripping",
		"testOutputAggregation",
		"buildOutputFiltering",
		"gitCompaction",
		"searchResultGrouping",
		"linterAggregation",
	] as const;

	for (const technique of booleanTechniques) {
		pi.registerCommand(`rtk-toggle-${technique}`, {
			description: `Toggle the ${technique} technique on/off`,
			handler: async (_args, ctx) => {
				config.techniques[technique] = !config.techniques[technique];
				ctx.ui.notify(
					`RTK ${technique} ${config.techniques[technique] ? "enabled" : "disabled"}`,
					config.techniques[technique] ? "info" : "warning"
				);
			},
		});
	}

	pi.registerCommand("rtk-toggle-truncation", {
		description: "Toggle output truncation on/off",
		handler: async (_args, ctx) => {
			config.techniques.truncation.enabled = !config.techniques.truncation.enabled;
			ctx.ui.notify(
				`RTK truncation ${config.techniques.truncation.enabled ? "enabled" : "disabled"}`,
				config.techniques.truncation.enabled ? "info" : "warning"
			);
		},
	});

	pi.registerCommand("rtk-toggle-sourceCodeFiltering", {
		description: "Toggle source code filtering on/off",
		handler: async (_args, ctx) => {
			config.techniques.sourceCodeFiltering.enabled = !config.techniques.sourceCodeFiltering.enabled;
			ctx.ui.notify(
				`RTK sourceCodeFiltering ${config.techniques.sourceCodeFiltering.enabled ? "enabled" : "disabled"}`,
				config.techniques.sourceCodeFiltering.enabled ? "info" : "warning"
			);
		},
	});

	pi.registerCommand("rtk-toggle-smartTruncation", {
		description: "Toggle smart truncation on/off",
		handler: async (_args, ctx) => {
			config.techniques.smartTruncation.enabled = !config.techniques.smartTruncation.enabled;
			ctx.ui.notify(
				`RTK smartTruncation ${config.techniques.smartTruncation.enabled ? "enabled" : "disabled"}`,
				config.techniques.smartTruncation.enabled ? "info" : "warning"
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
			const t = config.techniques;
			const summary = [
				`RTK enabled: ${enabled}`,
				`ansiStripping: ${t.ansiStripping}`,
				`truncation: enabled=${t.truncation.enabled}, maxChars=${t.truncation.maxChars}`,
				`sourceCodeFiltering: enabled=${t.sourceCodeFiltering.enabled}, level=${t.sourceCodeFiltering.level}`,
				`smartTruncation: enabled=${t.smartTruncation.enabled}, maxLines=${t.smartTruncation.maxLines}`,
				`testOutputAggregation: ${t.testOutputAggregation}`,
				`buildOutputFiltering: ${t.buildOutputFiltering}`,
				`gitCompaction: ${t.gitCompaction}`,
				`searchResultGrouping: ${t.searchResultGrouping}`,
				`linterAggregation: ${t.linterAggregation}`,
			].join("\n");
			ctx.ui.notify(summary, "info");
		},
	});


}
