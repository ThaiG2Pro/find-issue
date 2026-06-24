// apply-stack — apply a stack preset to a project.
// Seeds context/stack.md + conventions.md and installs the stack skill pack. On Kiro it also
// wires those skills to the right agents (merged into context-map.json) and re-runs the mapper;
// on Claude there is no context-map.json — skills are auto-discovered by living under
// <platform>/skills/, so the wiring steps are skipped.
//
// Usage:  node .kiro/tools/apply-stack.mjs <stack> [projectDir]
//         node .claude/tools/apply-stack.mjs <stack> [projectDir]
//         node <platform>/tools/apply-stack.mjs --list
// Stacks live at <platform>/stacks/<stack>/ (installed by `init`).

import { readFileSync, writeFileSync, existsSync, readdirSync, cpSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

// Copied into BOTH .kiro/tools/ and .claude/tools/; resolve the platform dir from this script's
// own install path so the same source applies a stack on either host.
const PLATFORM_DIR = fileURLToPath(import.meta.url).includes('/.claude/') ? '.claude' : '.kiro';
const IS_KIRO = PLATFORM_DIR === '.kiro';

const args = process.argv.slice(2);
const projectDir = resolve(args.find((a) => !a.startsWith('-') && a !== args[0]) || '.');
const kiro = join(projectDir, PLATFORM_DIR);
const stacksDir = join(kiro, 'stacks');

function listStacks() {
  if (!existsSync(stacksDir)) return [];
  return readdirSync(stacksDir).filter((d) => existsSync(join(stacksDir, d, 'preset.json')));
}

if (args.includes('--list') || args.length === 0) {
  const s = listStacks();
  console.log(s.length ? 'Available stacks:\n  ' + s.join('\n  ') : `No stacks at ${stacksDir}`);
  process.exit(0);
}

const stack = args[0];
const stackDir = join(stacksDir, stack);
if (!existsSync(join(stackDir, 'preset.json'))) {
  console.error(`✗ unknown stack "${stack}". Available: ${listStacks().join(', ') || '(none)'}`);
  process.exit(1);
}

const preset = JSON.parse(readFileSync(join(stackDir, 'preset.json'), 'utf8'));
console.log(`apply-stack: ${stack} → ${projectDir}`);

// 1. Seed context files (overwrite the templates for the files the preset provides)
const ctxSrc = join(stackDir, 'context');
let seeded = 0;
if (existsSync(ctxSrc)) {
  for (const f of readdirSync(ctxSrc)) {
    cpSync(join(ctxSrc, f), join(kiro, 'context', f));
    seeded++;
  }
}
console.log(`  ✓ seeded ${seeded} context file(s): ${(preset.contextFiles || []).join(', ')}`);

// 2. Install the stack skill pack
const skillsSrc = join(stackDir, 'skills');
let installed = 0;
if (existsSync(skillsSrc)) {
  for (const s of readdirSync(skillsSrc)) {
    cpSync(join(skillsSrc, s), join(kiro, 'skills', s), { recursive: true });
    installed++;
  }
}
console.log(`  ✓ installed ${installed} stack skill(s)`);

// 3 + 4. Kiro only: merge preset skills → context-map.json and re-wire agents. Claude has no
// context-map.json (skills are auto-discovered under .claude/skills/), so these steps are skipped.
if (IS_KIRO) {
  // 3. Merge preset skills → context-map.json (per agent, deduped)
  const mapPath = join(kiro, 'context-map.json');
  const map = JSON.parse(readFileSync(mapPath, 'utf8'));
  map.agents = map.agents || {};
  for (const [agent, skills] of Object.entries(preset.skills || {})) {
    map.agents[agent] = map.agents[agent] || { skills: [], knowledgeBase: [] };
    const set = new Set(map.agents[agent].skills || []);
    skills.forEach((s) => set.add(s));
    map.agents[agent].skills = [...set];
  }
  writeFileSync(mapPath, JSON.stringify(map, null, 2) + '\n');
  console.log('  ✓ merged stack skills into context-map.json');

  // 4. Re-wire
  console.log('  wiring:');
  const { applyContextMap } = await import('./context-map.mjs');
  applyContextMap({ kiroDir: kiro, log: (s) => console.log(s) });
} else {
  console.log(`  ✓ stack skills live under ${PLATFORM_DIR}/skills/ — Claude auto-discovers them (no context-map wiring needed)`);
}

console.log(`\n  Done. Stack "${stack}" applied. Review ${PLATFORM_DIR}/context/stack.md + conventions.md, then run the onboarder for the rest.`);
