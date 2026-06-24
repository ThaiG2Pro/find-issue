// apply-stack — apply a stack preset to a project.
// Seeds context/stack.md + conventions.md, installs the stack skill pack, wires those
// skills to the right agents (merged into context-map.json), and re-runs the mapper.
//
// Usage:  node .kiro/tools/apply-stack.mjs <stack> [projectDir]
//         node .kiro/tools/apply-stack.mjs --list
// Stacks live at .kiro/stacks/<stack>/ (installed by `init`).

import { readFileSync, writeFileSync, existsSync, readdirSync, cpSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { applyContextMap } from './context-map.mjs';

const args = process.argv.slice(2);
const projectDir = resolve(args.find((a) => !a.startsWith('-') && a !== args[0]) || '.');
const kiro = join(projectDir, '.kiro');
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
applyContextMap({ kiroDir: kiro, log: (s) => console.log(s) });
console.log(`\n  Done. Stack "${stack}" applied. Review .kiro/context/stack.md + conventions.md, then run the onboarder for the rest.`);
