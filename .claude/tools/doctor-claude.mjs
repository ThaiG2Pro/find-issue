// doctor-claude — structural health check for a Claude Code kit install.
//
// The Kiro doctor (doctor.mjs) validates agent JSON + resources[] + the context map — none of
// which exist on Claude. This is the Claude-target equivalent: it verifies that the things Claude
// DOES rely on are intact — CLAUDE.md @imports resolve, all commands/subagents exist, the
// "only the developer writes code" tool invariant holds, settings.json hooks point at installed
// scripts/tools, the workspace symlinks are live — then folds in context completeness.
//
// Usage:  node .claude/tools/doctor-claude.mjs [projectDir]
// Exit:   0 = no FAIL (WARN allowed)   1 = at least one FAIL

import { readFileSync, existsSync, readdirSync, lstatSync } from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { execSync } from 'node:child_process';

const projectDir = resolve(process.argv[2] || '.');
const cc = join(projectDir, '.claude');
const results = []; // {level: 'ok'|'warn'|'fail', msg}
const ok = (m) => results.push({ level: 'ok', msg: m });
const warn = (m) => results.push({ level: 'warn', msg: m });
const fail = (m) => results.push({ level: 'fail', msg: m });

if (!existsSync(cc)) { console.error(`✗ no .claude/ at ${projectDir} — run init --target claude first`); process.exit(1); }

// Parse the YAML frontmatter (the `--- … ---` block) of a command/agent .md into a flat object.
// These files use only simple `key: value` scalars, so a line parser is sufficient.
function frontmatter(file) {
  const src = readFileSync(file, 'utf8');
  const m = src.match(/^---\n([\s\S]*?)\n---/);
  if (!m) return null;
  const fm = {};
  for (const line of m[1].split('\n')) {
    const kv = line.match(/^([A-Za-z][\w-]*):\s*(.*)$/);
    if (kv) fm[kv[1]] = kv[2].trim();
  }
  return fm;
}

// 1. Required structure
for (const d of ['agents', 'agents/scripts', 'commands', 'skills', 'steering', 'context', 'tools']) {
  existsSync(join(cc, d)) ? ok(`dir .claude/${d}/`) : fail(`missing .claude/${d}/`);
}
existsSync(join(cc, 'settings.json')) ? ok('file .claude/settings.json') : fail('missing .claude/settings.json');

// Claude Code auto-loads BOTH ./CLAUDE.md and ./.claude/CLAUDE.md. The kit installs its entry file
// (the one carrying the @import wiring) to .claude/CLAUDE.md — a project may ALSO keep its own
// ./CLAUDE.md, and they coexist. Validate the KIT's file, so a user's import-less project doc at the
// root doesn't mask (or get mistaken for) the kit's wiring. Fall back to root only if absent.
const claudeMd = existsSync(join(cc, 'CLAUDE.md')) ? join(cc, 'CLAUDE.md')
  : existsSync(join(projectDir, 'CLAUDE.md')) ? join(projectDir, 'CLAUDE.md') : null;
if (claudeMd) ok(`file ${claudeMd === join(cc, 'CLAUDE.md') ? '.claude/CLAUDE.md' : 'CLAUDE.md'}`);
else fail('no CLAUDE.md at project root or .claude/ — Claude has no entry point');

// 2. CLAUDE.md @imports resolve. Claude has no context map — the wiring IS these import lines, and
//    @paths resolve RELATIVE TO THE CLAUDE.md FILE'S OWN DIRECTORY (not the project root). So the
//    correct prefix depends on where the file sits: at root use `@.claude/steering/x`; inside
//    .claude/ use `@steering/x`. A wrong prefix silently drops all steering+context at runtime —
//    the exact failure doctor.mjs can't see on Claude.
if (claudeMd) {
  const base = dirname(claudeMd);
  let imports = 0, broken = 0;
  for (const line of readFileSync(claudeMd, 'utf8').split('\n')) {
    const m = line.match(/^@(\S+)/);
    if (!m) continue;
    imports++;
    if (!existsSync(join(base, m[1]))) { fail(`CLAUDE.md @import does not resolve → @${m[1]} (relative to ${base})`); broken++; }
  }
  if (imports === 0) warn('CLAUDE.md has no @import lines — context/steering not wired');
  else if (broken === 0) ok(`all ${imports} CLAUDE.md @import(s) resolve`);
}

// 3. Commands + subagents present (the slash commands and the roles they spawn)
const EXPECT_COMMANDS = ['sdlc-full', 'sdlc-fast', 'analyst', 'architect', 'developer', 'qa', 'onboarder'];
const EXPECT_AGENTS = ['analyst', 'architect', 'developer', 'qa', 'onboarder'];
for (const [dir, expect, kind] of [['commands', EXPECT_COMMANDS, 'command'], ['agents', EXPECT_AGENTS, 'subagent']]) {
  const d = join(cc, dir);
  if (!existsSync(d)) continue;
  for (const name of expect) {
    existsSync(join(d, `${name}.md`)) ? ok(`${kind} /${name}`) : fail(`missing ${kind} .claude/${dir}/${name}.md`);
  }
}

// 4. Subagent frontmatter valid + the SECURITY INVARIANT: only `developer` may carry the Edit tool.
//    (Layer 1 of the 3 defense layers — a regression here silently lets a read-only role write code.)
const agentsDir = join(cc, 'agents');
if (existsSync(agentsDir)) {
  for (const name of EXPECT_AGENTS) {
    const f = join(agentsDir, `${name}.md`);
    if (!existsSync(f)) continue; // already FAILed above
    const fm = frontmatter(f);
    if (!fm) { fail(`subagent ${name}: no YAML frontmatter`); continue; }
    if (!fm.name) warn(`subagent ${name}: frontmatter has no \`name\``);
    if (fm.name && fm.name !== name) warn(`subagent ${name}: frontmatter name "${fm.name}" ≠ filename`);
    if (!fm.tools) { fail(`subagent ${name}: frontmatter has no \`tools\` — tool restriction not set`); continue; }
    const tools = fm.tools.split(',').map((t) => t.trim());
    const hasEdit = tools.includes('Edit') || tools.includes('MultiEdit');
    if (name === 'developer' && !hasEdit) fail('SECURITY: developer subagent is missing the Edit tool — it cannot write code');
    if (name !== 'developer' && hasEdit) fail(`SECURITY: ${name} subagent carries Edit — only developer may write code`);
  }
  ok('subagent tool invariant checked (only developer has Edit)');
}

// 5. settings.json valid + hooks/permissions point at scripts & tools that actually ship.
const settingsPath = join(cc, 'settings.json');
if (existsSync(settingsPath)) {
  let raw;
  try { raw = readFileSync(settingsPath, 'utf8'); JSON.parse(raw); ok('settings.json is valid JSON'); }
  catch (e) { fail(`settings.json invalid JSON (${e.message})`); raw = ''; }
  // every .claude/agents/scripts/<x>.py referenced by a hook must exist
  const scriptRefs = new Set([...raw.matchAll(/\.claude\/agents\/scripts\/([\w-]+\.py)/g)].map((m) => m[1]));
  let missingScript = 0;
  for (const s of scriptRefs) {
    if (!existsSync(join(cc, 'agents', 'scripts', s))) { fail(`settings.json hook → missing script .claude/agents/scripts/${s}`); missingScript++; }
  }
  if (scriptRefs.size && missingScript === 0) ok(`all ${scriptRefs.size} hook script(s) present`);
  // the two PreToolUse guards are the security backbone — warn loudly if either is absent
  for (const guard of ['check-shell-command.py', 'check-write-path.py']) {
    if (!raw.includes(guard)) warn(`settings.json does not wire ${guard} — role enforcement weakened`);
  }
}

// 6. Tools installed (the 4 Claude engines) + the core orchestration skill present
for (const t of ['context-check.mjs', 'apply-stack.mjs', 'pipeline-guard.mjs', 'cpp-guard.mjs']) {
  existsSync(join(cc, 'tools', t)) ? ok(`tool ${t}`) : fail(`missing .claude/tools/${t}`);
}
const skillsDir = join(cc, 'skills');
if (!existsSync(skillsDir) || readdirSync(skillsDir).length === 0) fail('.claude/skills/ is empty — no skills to auto-discover');
else existsSync(join(skillsDir, 'sdlc-orchestration-core', 'SKILL.md'))
  ? ok('core skill sdlc-orchestration-core present')
  : fail('missing skill sdlc-orchestration-core (the orchestrator commands wrap it)');

// 7. OpenSpec backend + workspace symlinks reachable from .claude/
try { execSync('openspec --version', { stdio: 'ignore' }); ok('openspec CLI installed'); }
catch { fail('openspec CLI missing — `npm i -g @fission-ai/openspec` (workspace depends on it)'); }
existsSync(join(projectDir, 'openspec', 'config.yaml')) ? ok('openspec/ workspace present')
  : fail('no openspec/config.yaml — run `openspec init --tools claude`');
for (const link of ['openspec', 'memory']) {
  const p = join(cc, link);
  if (!existsSync(p)) { warn(`no .claude/${link} symlink — run init`); continue; }
  try { lstatSync(p).isSymbolicLink() ? ok(`symlink .claude/${link}`) : warn(`.claude/${link} is not a symlink`); }
  catch { warn(`.claude/${link} unreadable`); }
}

// 8. Context completeness (same semantics doctor.mjs uses; context-check.mjs enforces in full)
const ctx = join(cc, 'context');
if (existsSync(ctx)) {
  let todo = 0, unknown = 0;
  for (const f of readdirSync(ctx).filter((f) => f.endsWith('.md'))) {
    const s = readFileSync(join(ctx, f), 'utf8');
    todo += (s.match(/<!--\s*TODO/g) || []).length;
    unknown += (s.match(/UNKNOWN — needs owner input/g) || []).length;
  }
  if (todo > 0) warn(`context not filled — ${todo} TODO marker(s) (run /onboarder; context-check enforces)`);
  else ok('context contract filled (0 TODO)');
  if (unknown > 0) warn(`${unknown} field(s) marked UNKNOWN — needs owner input`);
}

// Report
const pad = { ok: '✓', warn: '⚠', fail: '✗' };
console.log('  kit doctor (Claude) — ' + projectDir);
console.log('  ' + '─'.repeat(50));
for (const r of results) console.log(`  ${pad[r.level]} ${r.msg}`);
const fails = results.filter((r) => r.level === 'fail').length;
const warns = results.filter((r) => r.level === 'warn').length;
console.log('  ' + '─'.repeat(50));
console.log(`  ${fails === 0 ? '✓ HEALTHY' : '✗ ' + fails + ' FAIL'}${warns ? ` · ${warns} warning(s)` : ''}`);
process.exit(fails === 0 ? 0 : 1);
