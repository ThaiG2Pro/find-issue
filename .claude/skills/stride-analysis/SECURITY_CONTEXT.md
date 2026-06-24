# Security Context per Domain

Adjust threat priority theo domain và loại business:

## Payment / Finance

| Threat Category | High-Risk Items | Why | Example |
|-----------------|-----------------|-----|---------|
| **Tampering** | Transaction amount, status, destination | Fraud: modify payment amount hoặc đổi recipient | Modify order total từ 1M → 100k |
| **Information Disclosure** | Card data, account numbers, PII, payment status | PCI-DSS compliance, customer privacy | Exposed credit card via API response |
| **Elevation of Privilege** | Payment gateway access, discount approval, refund | Financial impact: unauthorized refunds/charges | User apply admin discount code |
| **Spoofing** | Bank account verification, 3D Secure | Fake payment verification, unauthorized account | Fake bank confirmation email |

**Test priorities:**
- Tampering: validate amount, validate recipient account
- Information Disclosure: never log/export card data, sanitize API responses
- Elevation: permission checks on discounts, refunds, transfers
- Spoofing: email verification, SMS OTP for high-value txns

---

## Admin CMS

| Threat Category | High-Risk Items | Why | Example |
|-----------------|-----------------|-----|---------|
| **Spoofing** | Admin login, 2FA bypass | Unauthorized access to admin panel | Brute force password, session hijack |
| **Elevation of Privilege** | Role assignment, permission matrix | Unauthorized access to sensitive operations | Promote user to admin, edit others' data |
| **Tampering** | Content modification, mass delete, SQL injection | Data integrity, data loss | Edit article publish date, delete users |
| **Repudiation** | Audit logs, change tracking | Lack of accountability | Admin deletes logs to hide unauthorized changes |

**Test priorities:**
- Spoofing: require 2FA, rate limit login, secure session storage
- Elevation: verify role before every action (per-record ACL), test role downgrades
- Tampering: validate all inputs, soft deletes with audit trail
- Repudiation: immutable audit logs, timestamp all changes

---

## Consumer App (Web/Mobile)

| Threat Category | High-Risk Items | Why | Example |
|-----------------|-----------------|-----|---------|
| **Information Disclosure** | PII (email, phone, DOB), user profile data, location | Privacy regulations (GDPR, CCPA) | API returns full profile in error message |
| **Spoofing** | Account takeover, password reset, OAuth | Access to private user data and actions | Reset token in email querystring (predictable) |
| **Denial of Service** | API rate limits, upload size limits, expensive operations | Service disruption, cost impact | Unlimited file upload → disk full |
| **Elevation of Privilege** | Direct Object Reference (IDOR), viewing others' data | Privacy breach, unauthorized access | Access user profile via /api/user/{id} manipulation |

**Test priorities:**
- Information Disclosure: verify error messages don't leak data, test PII minimization
- Spoofing: test password reset token entropy, rate limit login attempts
- DoS: test rate limits, file size caps, slow query protection
- Elevation: test IDOR: modify user ID in URL/payload, verify per-user access controls

---

## API Gateway / Integration Layer

| Threat Category | High-Risk Items | Why | Example |
|-----------------|-----------------|-----|---------|
| **Tampering** | Request/response manipulation, header injection | Message authenticity, header-based auth bypass | Inject X-User-ID header to fake auth |
| **Denial of Service** | Rate limiting, request size limits, timeout | Service availability | Flood with large requests, slow queries |
| **Information Disclosure** | API tokens in logs, sensitive headers, request/response bodies | Token theft, audit trail exposure | API key logged in error logs |
| **Elevation of Privilege** | API version bypasses, internal endpoint exposure | Unauthorized access to admin APIs | Call deprecated /api/v1/admin/users endpoint |

**Test priorities:**
- Tampering: verify signature/HMAC on requests, validate headers
- DoS: test rate limits per client, request size validation
- Information Disclosure: redact tokens from logs, strip sensitive headers from responses
- Elevation: disable deprecated API versions, isolate internal endpoints

---

## E-commerce / Catalog

| Threat Category | High-Risk Items | Why | Example |
|-----------------|-----------------|-----|---------|
| **Tampering** | Product price, inventory, description | Price manipulation fraud, inventory bypass | Modify product price in DOM, bypass stock check |
| **Information Disclosure** | Pricing logic, cost basis, competitor pricing | Business secret exposure | Exposed cost/margin in API |
| **Elevation of Privilege** | Inventory management, price override | Unauthorized discounts, stock manipulation | User marks out-of-stock item as in-stock |
| **DoS** | Inventory flood, search query explosion | Service disruption, performance degradation | Malicious search returning 1M results |

**Test priorities:**
- Tampering: validate price server-side, prevent concurrent inventory updates
- Information Disclosure: hide cost basis, never expose pricing algorithms
- Elevation: permission checks for stock/price edits, audit all changes
- DoS: pagination on search, inventory concurrency handling, query complexity limits

---

## Messaging / Social Features

| Threat Category | High-Risk Items | Why | Example |
|-----------------|-----------------|-----|---------|
| **Spoofing** | Sender identity, impersonation | Phishing, scam, defamation | Forge sender name in message |
| **Repudiation** | Message deletion, edit history | Accountability, evidence preservation | Attacker deletes message evidence |
| **Information Disclosure** | Private messages, drafts, deleted messages | Privacy violation, sensitive data leak | Access deleted messages via database |
| **Elevation of Privilege** | Permission to read others' DMs, broadcast as admin | Privacy breach, unauthorized messaging | Access other user's message thread |

**Test priorities:**
- Spoofing: verify sender identity, rate limit messages from new users
- Repudiation: immutable message logs, track edit history, soft deletes only
- Information Disclosure: end-to-end encryption for sensitive channels, redact deleted message content
- Elevation: permission checks per message thread, can't access if not participant

---

## Common High-Risk Patterns (across all domains)

| Pattern | Risk | Mitigation |
|---------|------|-----------|
| **Direct Object Reference (IDOR)** | Elevation, Information Disclosure | Per-record ACL check, never trust user input for ID verification |
| **Hardcoded Secrets** | Information Disclosure | Use env vars, secret manager, rotate regularly |
| **No Rate Limiting** | DoS | Implement per-user/IP rate limits, exponential backoff |
| **Insufficient Logging** | Repudiation | Log all sensitive actions with user ID, timestamp, change details |
| **SQL Injection** | Tampering, Information Disclosure | Parameterized queries, input validation |
| **XSS** | Information Disclosure, Elevation | Output encoding, CSP headers, input validation |
| **Weak Password Policy** | Spoofing | Min 12 chars, complexity rules, MFA enforcement |
