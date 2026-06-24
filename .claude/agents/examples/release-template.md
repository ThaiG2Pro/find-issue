---
name: release-template
description: >
  Template for {CHANGE_DIR}/release.md — the S6 release artifact the developer writes before
  `openspec archive`. Contains: release notes (ref AC-IDs), migration checklist, rollback plan,
  post-deploy smoke test, deploy strategy.
---

# Release — {ticket_id} ({change-name})
Date: {ISO date}
Deploy strategy: {direct | canary | blue-green}

## Release Notes
**Features**
- {feature} (AC-{ticket}-{NNN}, …)

**Bug fixes**
- {fix} (AC-{ticket}-{NNN})

**Breaking changes**
- {none, or describe + migration note}

## Migration Checklist
| Order | Migration | up() | down() | Destructive? | Backup step |
|-------|-----------|------|--------|--------------|-------------|
| 1 | {migration name} | ✅ | ✅ | {no / yes} | {n/a or backup plan} |

## Rollback Plan
1. {step to revert the deploy}
2. {step to roll back migrations (run down() in reverse order)}
3. {how to confirm the system is back to the prior good state}

## Post-Deploy Smoke Test
- [ ] {critical path 1} → {expected}
- [ ] {critical path 2} → {expected}
- [ ] Health endpoint returns success + dependency checks green
- [ ] Error rate / latency within budget for {N} min

## Archive
- [ ] `openspec archive "{change-name}"` run — spec deltas merged into the living spec, change moved to openspec/changes/archive/
