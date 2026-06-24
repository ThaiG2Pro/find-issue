# STRIDE Analysis Templates

## Threat Analysis Template (per AC / Endpoint)

```markdown
### [STRIDE] {Category}: {Threat Title}

**Affected AC/Endpoint**: {AC-id} / {endpoint path}

**Threat Description**:
{1-2 sentences mô tả scenario tấn công}

**Attack Vector**:
{Cách nào attacker có thể trigger}

**Impact**:
- {business/data impact}

**Mitigation**:
- {control/code pattern}
- {test case nên cover}
```

## Categories & Guiding Questions

| Category | Guiding Questions | Examples |
|----------|-------------------|----------|
| **S**poofing | Có thể giả mạo identity/user không? | Fake user, fake API token, session hijack |
| **T**ampering | Có thể modify data trong transit/storage không? | Modify request payload, DB corruption, file tampering |
| **R**epudiation | Có thể phủ nhận action đã thực hiện không? | Delete logs, lack of audit trail, no signature |
| **I**nformation Disclosure | Có thể leak sensitive data không? | Exposed API keys, SQL injection, sensitive data in logs |
| **D**enial of Service | Có thể crash/block service không? | Large file upload, infinite loop, unvalidated input |
| **E**levation of Privilege | Có thể bypass permission checks không? | Direct object reference (IDOR), missing authz, role confusion |

## Severity Calculation

```
Severity = Impact × Likelihood

**Impact levels:**
- High    : data breach, service down, financial loss
- Medium  : info leak, false action
- Low     : inconvenience, minor UX issue

**Likelihood levels:**
- High    : easy to exploit, no validation, obvious attack vector
- Medium  : requires effort, partially mitigated, some validation
- Low     : mitigations exist, difficult to exploit, requires prior access

**Severity mapping:**
- Critical  : High Impact × High Likelihood
- High      : High Impact × Medium Likelihood
- Medium    : Medium Impact × Medium/High Likelihood
- Low       : Low Impact / Low Likelihood
```

## Output Report Structure

```markdown
# [stride-analysis] STRIDE Threat Model — {ticket_id}

**Feature**: {tên feature}
**Requirement Version**: {lấy từ requirement_analysis.md}
**Analysis Date**: {ngày hôm nay}

---

## Executive Summary

- Total threats identified: {n}
- Critical: {n}, High: {n}, Medium: {n}, Low: {n}
- Recommendation: {Go / Conditional Go / No-Go} với security gate

---

## STRIDE Analysis

### 1. Spoofing Threats
[Liệt kê các threat phát hiện]

### 2. Tampering Threats
[...]

### 3. Repudiation Threats
[...]

### 4. Information Disclosure Threats
[...]

### 5. Denial of Service Threats
[...]

### 6. Elevation of Privilege Threats
[...]

---

## Security Test Strategy

**Threats to cover in qa-test-design**:
- [List Critical/High threats + suggested test case per threat]

**Threats to monitor (post-release)**:
- [List Medium/Low threats + monitoring approach]

---

## Recommendations for Dev

- [Code patterns / libraries to use]
- [Security headers / configs]
- [Authentication / authorization design]

---

## Gate Status

| Criterion | Status | Note |
|-----------|--------|------|
| No Critical threats | ✅/⚠️/❌ | {note} |
| All High threats have mitigation | ✅/⚠️/❌ | {note} |
| Test coverage planned | ✅/⚠️/❌ | {note} |
| **GATE** | **PASS / WARNING / BLOCK** | {recommendation} |
```

## Gate Conditions

### PASS ✅
- No Critical threats OR all mitigated
- High threats have clear mitigation + test plan
- No data flow security issues unaddressed

### WARNING ⚠️
- Medium threats tồn tại, cần security regression testing
- External service integration chưa verify security cách xử lý

### BLOCK ❌
- Critical threat không có mitigation
- Known vulnerability (e.g., hardcoded secrets, SQL injection vector)
- No authentication on sensitive endpoint
