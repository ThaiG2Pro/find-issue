---
name: stride-analysis
description: >
  STRIDE threat modeling — analyze a feature's security threats from the spec BEFORE
  implementation (Spoofing/Tampering/Repudiation/Info-disclosure/DoS/Elevation). Produces a
  threat list + mitigations + a security gate (PASS/WARNING/BLOCK). Run during S1/S2 (analyst —
  Step 4e, feeds Early Risk Flags) and/or S3 (architect, design security). Gated by
  `.kiro/sdlc.config.json → security.stride_analysis` (auto | always | never).
---

# stride-analysis — STRIDE Threat Modeling

> Catch design-level security holes at S2/S3 (cheap) instead of S5/production (expensive).
> Output feeds the analyst's Early Risk Flags, the architect's design security section, and
> the qa test design.

## When to run (honor the config)

Read `.kiro/sdlc.config.json → security.stride_analysis`:
- **`always`** → run for every feature.
- **`auto`** (default) → run only when the feature touches a sensitive area — auth/login,
  payment/billing, PII/personal data, tokens/secrets, file upload, admin/privilege, or any
  external integration. If none apply, skip and note "STRIDE: not applicable".
- **`never`** → skip entirely.

## Process

### 0. Input
- Read the change's `proposal.md` + spec deltas under `openspec/changes/<change>/` (and `design.md` if S3).
- Extract: feature description, ACs, API endpoints (method/path/payloads), data flows,
  external integrations, auth/authz requirements.

### 1. STRIDE analysis per AC / endpoint
- For each AC or endpoint, walk the 6 categories S/T/R/I/D/E (questions in `TEMPLATES.md`).
- Severity = Impact × Likelihood → Critical / High / Medium / Low.
- Record recommended mitigations + the test case each threat implies.

### 2. Domain tuning
- Identify the domain (Payment / Admin / Consumer / API Gateway / E-commerce / Messaging …).
- Use `SECURITY_CONTEXT.md` for that domain's high-risk threats; prioritize accordingly.

### 3. Write the report
- Output: `openspec/changes/<change>/stride-threat-model.md` (template in `TEMPLATES.md`).
- Include: Executive Summary + the 6 STRIDE sections + Security Test Strategy + Dev Recommendations.

### 4. Gate status
- **BLOCK** — a Critical threat with no mitigation; a known vuln (hardcoded secret, injection
  vector); a sensitive endpoint with no authn/authz.
- **WARNING** — Medium threats remain; external-integration security unverified.
- **PASS** — no Critical (or all mitigated), High threats have mitigation + test plan.

### 5. Output summary
```
[stride-analysis] {ticket_id} — {feature}
Threats: {n} (Critical {C} / High {H} / Medium {M} / Low {L})
Domain : {domain}
Gate   : PASS / WARNING / BLOCK
Report : openspec/changes/<change>/stride-threat-model.md
Feeds  : analyst Early Risk Flags · architect design security · qa-test-design
```

## Reference files
- `TEMPLATES.md` — per-threat template, STRIDE categories + guiding questions, severity calc,
  report structure, gate conditions.
- `SECURITY_CONTEXT.md` — domain-specific threat priorities + common patterns.

## Rules
- **No fake threats** — list only real, plausible ones.
- **Real severity** — judge from the actual design, not absurd worst-case.
- A `BLOCK` is a real gate: surface it to the SDLC orchestrator; do not let S3/S4 proceed on it.
- Medium/Low threats → note for post-release monitoring, don't block.
