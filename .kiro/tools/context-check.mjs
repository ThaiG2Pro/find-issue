// context-check — deterministic Completeness + Semantic gate for the context contract.
// Two passes, both deterministic (no LLM judgment):
//   1. Completeness — FAILS (exit 1) if any unfilled `<!-- TODO` marker or leftover
//      `{{PLACEHOLDER}}` token remains, or a required file is missing.
//   2. Semantic depth — for files that are TODO-free, FAILS if a required field is
//      present-but-empty / shallow (e.g. glossary < 5 terms, HTTP status policy states
//      no status semantics, a stack bullet has no value). This is what catches the
//      "filled the template but said nothing real" failure mode that pass 1 cannot.
// `UNKNOWN — needs owner input` is surfaced as an accepted gap (warning), never silent.
//
// Usage:  node .kiro/tools/context-check.mjs [projectDir]
// Exit:   0 = complete & deep   1 = incomplete / shallow / missing dir

import { readFileSync, existsSync, readdirSync } from 'node:fs';
import { join, resolve } from 'node:path';

const REQUIRED = ['project.md', 'stack.md', 'conventions.md', 'architecture.md', 'glossary.md', 'legacy-ref.md'];
const TODO_RE = /<!--\s*TODO/g;          // matches `<!-- TODO -->` AND `<!-- TODO: hint -->`
const UNKNOWN_RE = /UNKNOWN — needs owner input/g;
const TOKEN_RE = /\{\{[A-Z_]+\}\}/g;     // leftover init placeholders, e.g. {{PROJECT_TITLE}}
const MIN_GLOSSARY_TERMS = 5;

function count(s, re) { return (s.match(re) || []).length; }

// Body text between a `## Heading` line and the next `## ` heading (or EOF), trimmed.
function sectionBody(src, headingRe) {
  const lines = src.split('\n');
  const start = lines.findIndex((l) => headingRe.test(l));
  if (start === -1) return null;
  const body = [];
  for (let j = start + 1; j < lines.length; j++) {
    if (/^##\s/.test(lines[j])) break;
    body.push(lines[j]);
  }
  return body.join('\n').trim();
}

// Value after a `- **Label**:` bullet. null = label absent; '' = present but empty.
function bulletValue(src, label) {
  const esc = label.replace(/[.*+?^${}()|[\]\\/]/g, '\\$&');
  // [ \t] (not \s) so the match never spills onto the next line.
  const m = src.match(new RegExp('\\*\\*' + esc + '\\*\\*[ \\t]*:?[ \\t]*([^\\n]*)', 'i'));
  if (!m) return null;
  return m[1].trim().replace(/^[—\-–:\s]+$/, '');
}

function glossary(src) {
  if (/greenfield/i.test(src) && /\bTBD\b/i.test(src)) return { greenfield: true, count: 0 };
  const rows = src.split('\n').filter((l) => {
    const t = l.trim();
    if (!t.startsWith('|')) return false;
    const term = (t.split('|')[1] || '').trim();
    if (!term) return false;
    if (/^term$/i.test(term)) return false;     // header row
    if (/^:?-{2,}/.test(term)) return false;     // separator row
    return true;
  });
  return { greenfield: false, count: rows.length };
}

const projectDir = resolve(process.argv[2] || '.');
const ctxDir = join(projectDir, '.kiro', 'context');
if (!existsSync(ctxDir)) {
  console.error(`✗ no .kiro/context/ at ${projectDir}`);
  process.exit(1);
}

const present = readdirSync(ctxDir).filter((f) => f.endsWith('.md'));
const semantic = [];          // { file, msg } — present-but-shallow defects (FAIL)
let totalTodo = 0, totalUnknown = 0, totalTokens = 0, missingFiles = [];

console.log('  context completeness check');
console.log('  ' + '─'.repeat(46));

const src = {};
for (const f of REQUIRED) {
  if (!present.includes(f)) { missingFiles.push(f); console.log(`  ✗ ${f.padEnd(20)} MISSING`); continue; }
  src[f] = readFileSync(join(ctxDir, f), 'utf8');
  const todo = count(src[f], TODO_RE);
  const unk = count(src[f], UNKNOWN_RE);
  const tok = count(src[f], TOKEN_RE);
  totalTodo += todo; totalUnknown += unk; totalTokens += tok;
  const mark = todo === 0 && tok === 0 ? '✅' : '❌';
  console.log(`  ${mark} ${f.padEnd(20)} TODO=${todo}${tok ? `  TOKEN=${tok}` : ''}${unk ? `  UNKNOWN=${unk}` : ''}`);
}

// ── Pass 2: semantic depth — only on files that are already TODO-free (else pass 1 owns it)
function clean(f) { return src[f] && count(src[f], TODO_RE) === 0; }

if (clean('glossary.md')) {
  const g = glossary(src['glossary.md']);
  if (!g.greenfield && g.count < MIN_GLOSSARY_TERMS)
    semantic.push({ file: 'glossary.md', msg: `only ${g.count} term(s); need ≥ ${MIN_GLOSSARY_TERMS} (or "Greenfield — terms TBD")` });
}

if (clean('conventions.md')) {
  const status = sectionBody(src['conventions.md'], /^##\s+HTTP Status Policy/i);
  const STATUS_RE = /\b(2xx|4xx|5xx|[245]\d\d|status\s*code|always\s*200)\b/i;
  if (status === null)
    semantic.push({ file: 'conventions.md', msg: 'no "## HTTP Status Policy" section found' });
  else if (!STATUS_RE.test(status))
    semantic.push({ file: 'conventions.md', msg: 'HTTP Status Policy states no concrete status semantics (4xx/5xx/200/status code)' });

  const resp = sectionBody(src['conventions.md'], /^##\s+API Response Format/i);
  if (resp !== null && !/error/i.test(resp))
    semantic.push({ file: 'conventions.md', msg: 'API Response Format does not describe the error shape' });
}

if (clean('stack.md')) {
  const REQUIRED_BULLETS = ['Language', 'Web/App framework', 'Database', 'ORM / data layer', 'Test framework', 'Coverage gate', 'Package manager'];
  for (const label of REQUIRED_BULLETS) {
    const v = bulletValue(src['stack.md'], label);
    if (v === '') semantic.push({ file: 'stack.md', msg: `**${label}** has no value` });
    // label absent (v === null) is left to the human review — bullets may be renamed legitimately
  }
}

console.log('  ' + '─'.repeat(46));

if (semantic.length) {
  console.log('  semantic depth (shallow / empty required fields):');
  for (const s of semantic) console.log(`  ❌ ${s.file.padEnd(18)} ${s.msg}`);
  console.log('  ' + '─'.repeat(46));
}
if (totalUnknown) {
  console.log(`  ⚠ ${totalUnknown} field(s) marked "UNKNOWN — needs owner input" — surface these at hand-off.`);
}

const fail = totalTodo > 0 || totalTokens > 0 || missingFiles.length > 0 || semantic.length > 0;
if (fail) {
  const reasons = [];
  if (totalTodo) reasons.push(`${totalTodo} TODO marker(s)`);
  if (totalTokens) reasons.push(`${totalTokens} unsubstituted {{token}}(s)`);
  if (missingFiles.length) reasons.push(`${missingFiles.length} file(s) missing`);
  if (semantic.length) reasons.push(`${semantic.length} shallow field(s)`);
  console.log(`  ✗ INCOMPLETE — ${reasons.join(', ')}. Do NOT hand off.`);
  process.exit(1);
}
console.log('  ✓ COMPLETE — every required context file is filled and substantive.');
process.exit(0);
