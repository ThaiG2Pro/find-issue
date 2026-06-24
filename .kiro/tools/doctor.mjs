// doctor — health check for a kit install in a project.
// Verifies structure, agent configs, reference resolution, symlinks, and context state.
//
// Usage:  node .kiro/tools/doctor.mjs [projectDir]
// Exit:   0 = no FAIL (WARN allowed)   1 = at least one FAIL

import { readFileSync, existsSync, readdirSync, lstatSync } from 'node:fs';
import { join, resolve, normalize } from 'node:path';
import { execSync } from 'node:child_process';

const projectDir = resolve(process.argv[2] || '.');
const kiro = join(projectDir, '.kiro');
const results = []; // {level: 'ok'|'warn'|'fail', msg}
const ok = (m) => results.push({ level: 'ok', msg: m });
const warn = (m) => results.push({ level: 'warn', msg: m });
const fail = (m) => results.push({ level: 'fail', msg: m });

if (!existsSync(kiro)) { console.error(`✗ no .kiro/ at ${projectDir} — run init first`); process.exit(1); }

// 1. Required structure
for (const d of ['agents', 'skills', 'steering', 'context', 'tools']) {
  existsSync(join(kiro, d)) ? ok(`dir .kiro/${d}/`) : fail(`missing .kiro/${d}/`);
}
for (const f of ['context-map.json', 'tools/context-map.mjs', 'tools/context-check.mjs']) {
  existsSync(join(kiro, f)) ? ok(`file .kiro/${f}`) : fail(`missing .kiro/${f}`);
}

// 2. OpenSpec backend (workspace) + CLI
try { execSync('openspec --version', { stdio: 'ignore' }); ok('openspec CLI installed'); }
catch { fail('openspec CLI missing — `npm i -g @fission-ai/openspec` (workspace depends on it)'); }
existsSync(join(projectDir, 'openspec', 'config.yaml')) ? ok('openspec/ workspace present')
  : fail('no openspec/config.yaml — run `openspec init --tools kiro`');

// 3. Symlinks (workspace reachable from .kiro/)
for (const link of ['openspec', 'memory']) {
  const p = join(kiro, link);
  if (!existsSync(p)) { warn(`no .kiro/${link} symlink — run init`); continue; }
  try { lstatSync(p).isSymbolicLink() ? ok(`symlink .kiro/${link}`) : warn(`.kiro/${link} is not a symlink`); }
  catch { warn(`.kiro/${link} unreadable`); }
}

// 3. Agent configs valid + prompt/skill/kb refs resolve
const agentsDir = join(kiro, 'agents');
if (existsSync(agentsDir)) {
  let brokenRefs = 0;
  for (const file of readdirSync(agentsDir).filter((f) => f.endsWith('.json'))) {
    let d;
    try { d = JSON.parse(readFileSync(join(agentsDir, file), 'utf8')); }
    catch (e) { fail(`agent ${file}: invalid JSON (${e.message})`); continue; }
    const p = d.prompt || '';
    if (p.startsWith('file://') && !existsSync(normalize(join(agentsDir, p.slice(7))))) {
      fail(`agent ${file}: prompt missing → ${p}`); brokenRefs++;
    }
    for (const r of d.resources || []) {
      if (typeof r === 'string' && r.startsWith('skill://')) {
        if (!existsSync(r.slice(8))) { fail(`agent ${file}: skill ref missing → ${r}`); brokenRefs++; }
      } else if (r && r.type === 'knowledgeBase') {
        const src = (r.source || '').replace(/^file:\/\/\.\//, '');
        if (src && !existsSync(join(projectDir, src))) { fail(`agent ${file}: kb ref missing → ${r.source}`); brokenRefs++; }
      }
    }
  }
  if (brokenRefs === 0) ok('all agent prompt/skill/kb references resolve');
}

// 4. Context completeness (delegate to context-check semantics)
const ctx = join(kiro, 'context');
if (existsSync(ctx)) {
  let todo = 0, unknown = 0;
  for (const f of readdirSync(ctx).filter((f) => f.endsWith('.md'))) {
    const s = readFileSync(join(ctx, f), 'utf8');
    todo += (s.match(/<!--\s*TODO/g) || []).length;
    unknown += (s.match(/UNKNOWN — needs owner input/g) || []).length;
  }
  if (todo > 0) warn(`context not filled — ${todo} TODO marker(s) (run onboarder; context-check enforces)`);
  else ok('context contract filled (0 TODO)');
  if (unknown > 0) warn(`${unknown} field(s) marked UNKNOWN — needs owner input`);
}

// Report
const pad = { ok: '✓', warn: '⚠', fail: '✗' };
console.log('  kit doctor — ' + projectDir);
console.log('  ' + '─'.repeat(50));
for (const r of results) console.log(`  ${pad[r.level]} ${r.msg}`);
const fails = results.filter((r) => r.level === 'fail').length;
const warns = results.filter((r) => r.level === 'warn').length;
console.log('  ' + '─'.repeat(50));
console.log(`  ${fails === 0 ? '✓ HEALTHY' : '✗ ' + fails + ' FAIL'}${warns ? ` · ${warns} warning(s)` : ''}`);
process.exit(fails === 0 ? 0 : 1);
