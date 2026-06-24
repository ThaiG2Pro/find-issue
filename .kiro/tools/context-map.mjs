// context-map engine
// Reads context-map.json and (re)writes the `resources` array of each Kiro agent .json.
// A path that does not exist is SKIPPED — the kit never emits a broken reference.
//
// Usage as module:  import { applyContextMap } from './lib/context-map.mjs'
//                    applyContextMap({ kiroDir, mapPath })
// Usage as CLI:      node bin/lib/context-map.mjs [projectDir] [--map <path>]

import { readFileSync, writeFileSync, existsSync, readdirSync } from 'node:fs';
import { join, dirname, resolve, basename } from 'node:path';
import { fileURLToPath } from 'node:url';

/**
 * @param {object} o
 * @param {string} o.kiroDir   absolute path to the project's .kiro/ dir
 * @param {string} [o.mapPath] path to context-map.json (defaults to <kiroDir>/context-map.json,
 *                             falling back to the kit's bundled copy)
 * @param {(s:string)=>void} [o.log]
 * @returns {{agent:string, skills:number, kb:number, skipped:string[]}[]}
 */
export function applyContextMap({ kiroDir, mapPath, log = () => {} }) {
  const projectRoot = dirname(kiroDir);
  const resolvedMap = mapPath
    || (existsSync(join(kiroDir, 'context-map.json')) ? join(kiroDir, 'context-map.json') : null);
  if (!resolvedMap || !existsSync(resolvedMap)) {
    throw new Error(`context-map.json not found (looked at ${resolvedMap || join(kiroDir, 'context-map.json')})`);
  }
  const map = JSON.parse(readFileSync(resolvedMap, 'utf8'));
  const always = map.always || {};
  const extraDocs = map.extraDocs || {};

  const agentsDir = join(kiroDir, 'agents');
  const agentFiles = readdirSync(agentsDir).filter((f) => f.endsWith('.json'));
  const report = [];

  for (const file of agentFiles) {
    const name = basename(file, '.json');
    const cfg = (map.agents && map.agents[name]) || { skills: [], knowledgeBase: [] };
    const jsonPath = join(agentsDir, file);
    const agent = JSON.parse(readFileSync(jsonPath, 'utf8'));

    const resources = [];
    const skipped = [];

    // 1. skills → skill:// (existence checked against .kiro/skills/<name>/SKILL.md)
    const skills = [...(always.skills || []), ...(cfg.skills || [])];
    let nSkill = 0;
    for (const s of dedupe(skills)) {
      if (existsSync(join(kiroDir, 'skills', s, 'SKILL.md'))) {
        resources.push(`skill://.kiro/skills/${s}/SKILL.md`);
        nSkill++;
      } else skipped.push(`skill:${s}`);
    }

    // 2. knowledgeBase (kiro-relative) → file://./.kiro/<entry>
    //    agents with inheritAlways:false (e.g. a hook-only utility agent) skip the shared `always` set
    const inheritAlways = cfg.inheritAlways !== false;
    const kb = [...(inheritAlways ? (always.knowledgeBase || []) : []), ...(cfg.knowledgeBase || [])];
    let nKb = 0;
    for (const e of dedupe(kb)) {
      if (existsSync(join(kiroDir, e))) {
        resources.push(kbEntry(`file://./.kiro/${e}`, e));
        nKb++;
      } else skipped.push(`kb:.kiro/${e}`);
    }

    // 3. extraDocs (project-root-relative) → file://./<entry>
    for (const d of dedupe(extraDocs[name] || [])) {
      if (typeof d !== 'string' || d.startsWith('$')) continue;
      if (existsSync(join(projectRoot, d))) {
        resources.push(kbEntry(`file://./${d}`, d));
        nKb++;
      } else skipped.push(`doc:${d}`);
    }

    agent.resources = resources;
    writeFileSync(jsonPath, JSON.stringify(agent, null, 2) + '\n');
    report.push({ agent: name, skills: nSkill, kb: nKb, skipped });
    log(`  ${name.padEnd(11)} skills=${nSkill} kb=${nKb}${skipped.length ? ` (skipped ${skipped.length})` : ''}`);
  }
  return report;
}

function dedupe(arr) { return [...new Set(arr)]; }

// Build a Kiro knowledgeBase resource entry with a derived name.
function kbEntry(source, entry) {
  const tail = entry.replace(/\.[a-z]+$/i, '').split('/').pop();
  const name = tail === 'specs' ? 'SpecsHistory'
    : tail.replace(/(^|[-_])([a-z])/g, (_, s, c) => (s ? '' : '') + c.toUpperCase());
  return {
    type: 'knowledgeBase',
    source,
    name,
    indexType: 'best',
    autoUpdate: entry === 'specs',
  };
}

// ---- CLI ----
if (resolve(process.argv[1]) === resolve(fileURLToPath(import.meta.url))) {
  const args = process.argv.slice(2);
  const mapIdx = args.indexOf('--map');
  const mapPath = mapIdx >= 0 ? resolve(args[mapIdx + 1]) : undefined;
  const projectDir = resolve(args.find((a) => !a.startsWith('--') && a !== (mapIdx >= 0 ? args[mapIdx + 1] : '')) || '.');
  const kiroDir = join(projectDir, '.kiro');
  if (!existsSync(kiroDir)) { console.error(`✗ no .kiro/ at ${projectDir}`); process.exit(1); }
  console.log(`context-map → ${kiroDir}`);
  applyContextMap({ kiroDir, mapPath, log: (s) => console.log(s) });
  console.log('done.');
}
