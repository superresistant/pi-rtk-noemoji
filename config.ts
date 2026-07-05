import { readFile } from "fs/promises";
import { resolve } from "path";
import { homedir } from "os";

export interface RtkConfig {
	enabled: boolean;
	logSavings: boolean;
	showUpdateEvery: number;
	techniques: {
		ansiStripping: boolean;
	};
}

export const DEFAULT_CONFIG: RtkConfig = {
	enabled: true,
	logSavings: true,
	showUpdateEvery: 10,
	techniques: {
		ansiStripping: true,
	},
};

export function mergeConfig(base: RtkConfig, override: Partial<RtkConfig>): RtkConfig {
	const rawShowUpdateEvery = override.showUpdateEvery;
	const showUpdateEvery =
		typeof rawShowUpdateEvery === "number" && Number.isInteger(rawShowUpdateEvery)
			? Math.max(0, rawShowUpdateEvery)
			: base.showUpdateEvery;

	return {
		...base,
		...override,
		showUpdateEvery,
		techniques: {
			...base.techniques,
			...(override.techniques || {}),
		},
	};
}

export async function loadConfig(cwd: string): Promise<RtkConfig> {
	// Try loading from project directory first, then fall back to global config
	const paths = [
		resolve(cwd, ".pi", "rtk-config.json"),
		resolve(homedir(), ".pi", "agent", "rtk-config.json"),
	];

	for (const configPath of paths) {
		try {
			const content = await readFile(configPath, "utf-8");
			const parsed = JSON.parse(content) as Partial<RtkConfig>;
			return mergeConfig(DEFAULT_CONFIG, parsed);
		} catch (error) {
			// Continue to next path
		}
	}

	return DEFAULT_CONFIG;
}
