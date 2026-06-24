---
name: security-audit
description: >
  Deep OWASP security audit cho request handlers + services (any stack).
  Secrets, input validation, SQL injection, auth guards, logging PII, XSS, CSRF, file uploads, security headers.
  Dùng khi audit toàn module hoặc trước khi merge feature nhạy cảm.
---

# Security Audit — issues-sum

Deep security review theo OWASP Top 10, align với `.kiro/steering/security.md`.

> **Stack-agnostic**: Code blocks below are **NestJS/Prisma examples** — the OWASP categories and checklist items are universal. For Laravel / Next.js / other stacks, apply the equivalent mechanism (see `context/stack.md`): e.g. validation = class-validator DTO **or** Laravel FormRequest **or** zod schema; parameterized query = Prisma **or** Eloquent/query bindings; guards = NestJS `@UseGuards` **or** Laravel middleware/policies **or** Next.js middleware.

## When to Activate

- Audit module auth, payment, user, order trước khi merge
- Feature mới có xử lý input từ external sources
- S5 QA cho features nhạy cảm
- Periodic security review (monthly hoặc sau thay đổi lớn)

## How to Use

```
Dùng skill security-audit để audit src/domain/merchant-access/
Dùng skill security-audit để audit src/interface/controllers/v6.controller.ts
```

## Security Checklist

### 1. Secrets Management

```typescript
// ❌ CRITICAL
const apiKey = 'sk_live_abc123xyz';
const jwtSecret = 'super-secret-key';

// ✅ MUST
const apiKey = process.env.API_KEY;
if (!apiKey) throw new Error('API_KEY not configured');
```

- [ ] No hardcoded API keys, passwords, tokens, encryption keys
- [ ] All secrets from environment variables
- [ ] `.env` in `.gitignore`
- [ ] `.env.example` exists with placeholder values

### 2. Input Validation

```typescript
export class CreateUserDto {
  @IsEmail()
  @IsNotEmpty()
  email: string;

  @IsString()
  @MinLength(8)
  @MaxLength(100)
  @Matches(/^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)/)
  password: string;

  @IsEnum(UserRole)
  role: UserRole;
}

// Global pipe (main.ts)
app.useGlobalPipes(new ValidationPipe({
  whitelist: true,
  forbidNonWhitelisted: true,
  transform: true,
}));
```

- [ ] All DTOs have validation decorators
- [ ] `@IsNotEmpty()` on required fields, `@IsOptional()` on optional
- [ ] String length limits (`@MaxLength()`)
- [ ] `whitelist: true` + `forbidNonWhitelisted: true` enabled globally

### 3. SQL Injection Prevention

```typescript
// ❌ DANGEROUS
const query = `SELECT * FROM users WHERE email = '${userEmail}'`;

// ✅ Prisma parameterized
const user = await prisma.user.findFirst({ where: { email: userEmail } });

// ✅ QueryBuilder
const users = await this.repo
  .createQueryBuilder('user')
  .where('user.email = :email', { email: userEmail })
  .getMany();
```

- [ ] No raw SQL with string concatenation
- [ ] All queries use the ORM's parameterized approach (Prisma / Eloquent bindings / TypeORM QueryBuilder params)
- [ ] No `query()` / `DB::raw()` with interpolated strings

### 4. Authentication & Authorization

```typescript
@UseGuards(JwtAuthGuard, RolesGuard)
@Roles('ADMIN', 'OPERATOR')
@Delete(':id')
async delete(@Param('id') id: string) { }
```

- [ ] Auth guards on all protected endpoints
- [ ] RBAC implemented — no sensitive endpoints without guards
- [ ] Password hashing (bcrypt/argon2)
- [ ] JWT with expiration
- [ ] Rate limiting on auth endpoints

### 5. Logging Security (P1)

```typescript
// ❌ NEVER
logger.info('User login', { email: user.email, password: user.password });
logger.info('Auth', { token: req.headers.authorization });

// ✅ ALWAYS
logger.info('User login', { user_id: user.id, email: maskEmail(user.email) });
```

- [ ] No passwords in logs
- [ ] No tokens (JWT, API keys, session)
- [ ] No credit card numbers
- [ ] No PII: email, phone, address (unless masked)
- [ ] No secret keys

### 6. XSS + Security Headers

```typescript
app.use(helmet({
  contentSecurityPolicy: true,
  hsts: true,
  frameguard: true,
  hidePoweredBy: true,
  noSniff: true,
  xssFilter: true,
}));
```

- [ ] Helmet configured with CSP, HSTS, X-Frame-Options
- [ ] User input sanitized before rendering (DOMPurify for frontend)
- [ ] No `dangerouslySetInnerHTML` without sanitization

### 7. File Upload Security

- [ ] File type validation (whitelist MIME types)
- [ ] File size limits enforced
- [ ] Filename sanitized — no path traversal
- [ ] Store outside webroot, generate random filenames

### 8. OWASP Top 10 Quick Check

| # | Threat | Check |
|---|--------|-------|
| A01 | Broken Access Control | RBAC + guards + resource ownership |
| A02 | Crypto Failures | HTTPS + bcrypt + encrypt sensitive data |
| A03 | Injection | Parameterized queries + input validation |
| A04 | Insecure Design | Security reviewed in S3 design phase |
| A05 | Security Misconfiguration | Debug off in prod + security headers |
| A06 | Vulnerable Components | dependency audit in CI (npm/yarn audit, composer audit, Trivy) |
| A07 | Auth Failures | Strong password policy + JWT expiry |
| A08 | Data Integrity | Lock files + verify deps |
| A09 | Logging Failures | Structured logging + no PII |
| A10 | SSRF | Validate URLs + whitelist domains |

## Output Format

```markdown
## Security Audit: {ModuleName}

### 🔴 Critical (Must Fix Before Merge)
- `user.service.ts:45` — Hardcoded JWT secret [Sonar S2068]
- `auth.controller.ts:23` — Password logged in plain text [Sonar S6437]

### 🟠 High (Fix Soon)
- `product.controller.ts` — Missing @UseGuards on DELETE endpoint
- `order.service.ts:67` — SQL concatenation instead of parameterized query

### 🟡 Medium (Should Fix)
- `user.dto.ts` — Missing @MaxLength on 'bio' field
- `payment.service.ts` — No rate limiting on payment endpoint

### ✅ Passed
- All DTOs have validation decorators
- No PII in logging statements
- Helmet configured correctly

### Summary: Critical: X | High: Y | Medium: Z | Passed: N
```
