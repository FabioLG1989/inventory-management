#!/usr/bin/env node
/**
 * Layered tool-default resolver for the deterministic preflight.
 *
 * Resolves, per tool and per argument, the level 2-4 baseline in fixed order:
 *   personal (developer's git-ignored file) → project (framework-config.json
 *   tool_defaults) → shipped (scripts/tool-defaults.json). Level 1 (CLI
 *   switches) is applied later by the skill, which is the only thing that knows
 *   the flags it was invoked with.
 *
 * Pure Node builtins — no build, no dependencies — so it runs in any user
 * project where Node is present, mirroring the sibling preflight scripts.
 * Fail-open by construction: an unreadable or absent source degrades to the
 * next level, an unrecognized value is skipped and named in `diagnostics`, and
 * the process ALWAYS prints a valid object and exits 0. The caller embeds the
 * output blindly and can never abort on it.
 *
 * Usage: node resolve-tool-defaults.mjs --registry <path> --config <path> --personal <path>
 * Emits: { "tools": { "<tool>": { values, provenance, diagnostics } } } on stdout.
 */
import { readFileSync } from 'node:fs';

function arg(flag) {
  const i = process.argv.indexOf(flag);
  return i >= 0 ? process.argv[i + 1] : undefined;
}

function readJson(path) {
  if (!path) return null;
  try {
    const parsed = JSON.parse(readFileSync(path, 'utf-8'));
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function section(bag, tool) {
  const s = bag && bag[tool];
  return s && typeof s === 'object' && !Array.isArray(s) ? s : null;
}

const registry = readJson(arg('--registry')) ?? {};
const config = readJson(arg('--config'));
const personal = readJson(arg('--personal'));
const project = config && section(config, 'tool_defaults') ? config['tool_defaults'] : null;

const tools = {};

for (const [tool, spec] of Object.entries(registry)) {
  if (!spec || typeof spec !== 'object') continue;

  const personalSection = section(personal, tool);
  const projectSection = section(project, tool);
  const values = {};
  const provenance = {};
  const diagnostics = [];

  for (const [key, argSpec] of Object.entries(spec)) {
    const expectedType = argSpec && argSpec.type;
    const sources = [
      ['personal', personalSection],
      ['project', projectSection],
    ];

    let settled = false;
    for (const [source, bag] of sources) {
      if (!bag || !(key in bag)) continue;
      const value = bag[key];
      if (typeof value !== expectedType) {
        diagnostics.push(
          `${tool}.${key}: ignored ${JSON.stringify(value)} from ${source} (expected ${expectedType}); falling through`,
        );
        continue;
      }
      values[key] = value;
      provenance[key] = source;
      settled = true;
      break;
    }

    if (!settled) {
      values[key] = argSpec ? argSpec.default : undefined;
      provenance[key] = 'shipped';
    }
  }

  tools[tool] = { values, provenance, diagnostics };
}

process.stdout.write(JSON.stringify({ tools }));
