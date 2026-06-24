// pipeline-guard — deterministic phase-order + gate guard for an OpenSpec change.
// The orchestrator (sdlc-full / sdlc-fast) MUST call this before routing or approving a gate.
// It converts "run phases in order, don't skip, don't jump the fence" from prompt-trust into
// an exit code, using the work `type`+`phases` persisted in _state.json and the declarative
// phase/gate catalogs in pipelines.json.
//
// Usage:
//   node .kiro/tools/pipeline-guard.mjs [projectDir] [--change <name>] [--gate <PHASE>]
//     (no --gate)     → status check: validate type/phase legality, print current + next phase.
//     --gate <PHASE>  → may the gate at <PHASE> be approved NOW? (at this phase, artifacts
//                       present, every earlier gated phase already passed).
// Exit: 0 = legal / gate may pass   1 = illegal state, skipped step, or fence-jump
//
// State contract (written by the orchestrator): _state.json carries
//   type, phases[], current_phase, and gates{ "<PHASE>": "passed" } recorded on each approval.

import { readFileSync, existsSync, readdirSync, statSync } from 'node:fs';
import { join, resolve } from 'node:path';

// Artifacts that must exist in <CHANGE_DIR> before a phase's gate can pass.
// (Deterministic filenames — independent of phaseCatalog's prose `produces`.)
const PHASE_ARTIFACTS = {
  S1: ['proposal.md'],
  S2: ['proposal.md'],                 // + a spec delta under specs/ (checked specially)
  S3: ['design.md', 'tasks.md'],
  S4: ['dev-test-report.md'],
  S5: ['qa-report.md'],
  S6: [],                              // terminal (archive); no pre-artifact
};

function die(msg) { console.log(`  ✗ ${msg}`); process.exit(1); }
function readJson(p) { try { return JSON.parse(readFileSync(p, 'utf8')); } catch { return null; } }

// ---- args ----
const argv = process.argv.slice(2);
let projectDir = '.', changeName = null, gatePhase = null;
for (let i = 0; i < argv.length; i++) {
  const a = argv[i];
  if (a === '--change') changeName = argv[++i];
  else if (a === '--gate') gatePhase = (argv[++i] || '').toUpperCase();
  else if (!a.startsWith('--')) projectDir = a;
}
projectDir = resolve(projectDir);

// ---- load pipelines.json ----
const pipelines = readJson(join(projectDir, '.kiro', 'pipelines.json'));
if (!pipelines) die(`no .kiro/pipelines.json at ${projectDir}`);
const { phaseCatalog = {}, types = {} } = pipelines;

// ---- resolve the active change dir ----
const changesBase = join(projectDir, 'openspec', 'changes');
function resolveChangeDir() {
  if (changeName) {
    const d = join(changesBase, changeName);
    return existsSync(join(d, '_state.json')) ? d : null;
  }
  if (!existsSync(changesBase)) return null;
  const cands = [];
  for (const n of readdirSync(changesBase)) {
    if (n === 'archive') continue;
    const st = join(changesBase, n, '_state.json');
    if (existsSync(st)) cands.push([statSync(st).mtimeMs, join(changesBase, n)]);
  }
  cands.sort((a, b) => b[0] - a[0]);
  return cands.length ? cands[0][1] : null;
}
const CHANGE_DIR = resolveChangeDir();
if (!CHANGE_DIR) die(changeName ? `no _state.json in change "${changeName}"` : 'no active change with _state.json under openspec/changes/');

// ---- load state ----
const state = readJson(join(CHANGE_DIR, '_state.json'));
if (!state) die(`unreadable _state.json in ${CHANGE_DIR}`);

const type = state.type;
const current = (state.current_phase || 'NEW').toUpperCase();
// A phase may carry a sub-phase suffix while an agent works through mini-gates (e.g. "S3-B" during
// architect's design loop). For order/legality checks we compare the base phase; `current` keeps the
// raw value for display so the user still sees the precise sub-phase.
const currentBase = current.split('-')[0];
const gates = state.gates || {};
const optional = (type && types[type] && types[type].optionalPhases) || [];

// type validity
if (!type || !types[type]) die(`_state.json type "${type}" is not a known pipeline (have: ${Object.keys(types).join(', ')}). Cannot guard.`);
// phases: prefer persisted, fall back to pipelines, and flag drift.
const declared = types[type].phases || [];
const phases = (Array.isArray(state.phases) && state.phases.length ? state.phases : declared).map((p) => p.toUpperCase());
const driftWarn = state.phases && JSON.stringify(state.phases.map((p) => p.toUpperCase())) !== JSON.stringify(declared.map((p) => p.toUpperCase()));

console.log(`  pipeline-guard · change=${CHANGE_DIR.split('/').pop()} · type=${type} · phases=${phases.join('→')} · current=${current}`);
if (driftWarn) console.log(`  ⚠ persisted phases differ from pipelines.json[${type}].phases (${declared.join('→')}) — using persisted.`);

// current_phase legality (NEW = not started, DONE/ARCHIVED = finished)
const SENTINELS = ['NEW', 'DONE', 'ARCHIVED'];
if (!SENTINELS.includes(currentBase) && !phases.includes(currentBase)) {
  die(`ILLEGAL STATE: current_phase ${current} is not in the ${type} pipeline (${phases.join('→')}). The change is running the wrong pipeline or state is corrupt.`);
}

function nextPhase() {
  if (currentBase === 'NEW') return phases[0] || null;
  const i = phases.indexOf(currentBase);
  return i >= 0 && i < phases.length - 1 ? phases[i + 1] : null;
}

// earlier gated phases that must already be 'passed' before PHASE (skip optional+gateless).
function unmetPriorGates(phase) {
  const stop = phases.indexOf(phase);
  const unmet = [];
  for (let i = 0; i < stop; i++) {
    const p = phases[i];
    const hasGate = phaseCatalog[p] && phaseCatalog[p].gate;
    if (!hasGate) continue;                 // e.g. S1 has no gate
    if (optional.includes(p)) continue;      // optional phase may be legitimately skipped
    if (gates[p] !== 'passed') unmet.push(`${p} (${phaseCatalog[p].gate})`);
  }
  return unmet;
}

function artifactsPresent(phase) {
  const missing = (PHASE_ARTIFACTS[phase] || []).filter((f) => !existsSync(join(CHANGE_DIR, f)));
  if (phase === 'S2') {
    const specsDir = join(CHANGE_DIR, 'specs');
    const hasDelta = existsSync(specsDir) && readdirSync(specsDir).length > 0;
    if (!hasDelta) missing.push('specs/** (≥1 requirement spec delta)');
  }
  // S5: the test-case deliverable is required ONLY when the pipeline selected it
  // (_state.json.testcase_export ∈ {xlsx,md}); `none` or a legacy state without the key skips it.
  // The qa generator may fall back to .csv when openpyxl is absent, so xlsx accepts xlsx OR csv.
  if (phase === 'S5') {
    const te = String(state.testcase_export || '').toLowerCase();
    if (te === 'xlsx' || te === 'md') {
      const cands = te === 'md' ? ['qa/testcases.md'] : ['qa/testcases.xlsx', 'qa/testcases.csv'];
      if (!cands.some((f) => existsSync(join(CHANGE_DIR, f)))) {
        missing.push(`${cands.join(' or ')} (testcase_export=${te})`);
      }
    }
  }
  return missing;
}

// ---- mode: gate check ----
if (gatePhase) {
  if (!phases.includes(gatePhase)) die(`ILLEGAL: ${gatePhase} is not a phase of the ${type} pipeline (${phases.join('→')}).`);
  const gateName = phaseCatalog[gatePhase] && phaseCatalog[gatePhase].gate;
  if (!gateName) die(`${gatePhase} has no gate in phaseCatalog — nothing to approve here.`);
  if (currentBase !== gatePhase) die(`OUT OF ORDER: you are at ${current}, not ${gatePhase}. Cannot approve the ${gateName} gate now.`);

  const unmet = unmetPriorGates(gatePhase);
  if (unmet.length) die(`FENCE-JUMP: earlier gate(s) not passed before ${gatePhase}: ${unmet.join(', ')}. Pass them first.`);

  const missing = artifactsPresent(gatePhase);
  if (missing.length) die(`MISSING ARTIFACTS for ${gatePhase} (${gateName}): ${missing.join(', ')}. The phase agent must produce these before the gate.`);

  // CPP context contract (deterministic) — the orchestrator's prose "CPP Contract Checks" turned
  // into an exit code, so a gate cannot pass when the handoff baton (handoff/decisions/glossary/
  // state) is missing — even if both the role agent AND the orchestrator forgot to verify it.
  try {
    const { checkCpp, checkTrailing } = await import('./cpp-guard.mjs');
    const cpp = checkCpp({ changeDir: CHANGE_DIR, gatePhase });
    if (!cpp.ok) die(`MISSING CONTEXT (CPP) for ${gatePhase} (${gateName}): ${cpp.problems.join('; ')}. The phase agent must write its handoff/decisions/glossary/state baton before the gate.`);
    // Trailing: side-effects the orchestrator owed at the PRIOR gate's approval (cross-spec + progress).
    const trail = checkTrailing({ projectRoot: projectDir, changeDir: CHANGE_DIR, state });
    if (!trail.ok) die(`MISSING RECORDS (orchestrator) before ${gatePhase} (${gateName}): ${trail.problems.join('; ')}. The orchestrator must record these when approving the prior gate.`);
  } catch (e) {
    if (e && e.code === 'ERR_MODULE_NOT_FOUND') {
      console.log('  ⚠ cpp-guard.mjs not found — CPP context NOT enforced (re-run init to install it).');
    } else throw e;
  }

  const next = nextPhase();
  console.log(`  ✓ ${gateName} gate at ${gatePhase} MAY be approved (artifacts present, prior gates passed).`);
  console.log(`  NEXT after approval: ${next ? next + ' (' + ((phaseCatalog[next] && phaseCatalog[next].agent) || '?') + ')' : 'ARCHIVE — final phase, run openspec archive'}`);
  process.exit(0);
}

// ---- mode: status check ----
const next = nextPhase();
if (current === 'NEW') {
  const first = phases[0];
  console.log(`  ✓ legal. Not started — first phase: ${first} (${(phaseCatalog[first] && phaseCatalog[first].agent) || '?'}).`);
} else if (!next) {
  console.log(`  ✓ legal. At final phase ${current} — after its gate, run openspec archive.`);
} else {
  console.log(`  ✓ legal. current=${current} → next legal phase: ${next} (${(phaseCatalog[next] && phaseCatalog[next].agent) || '?'}).`);
}
process.exit(0);
