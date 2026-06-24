---
name: security-review
description: >
  Security review cho NestJS + issues-sum. Input validation, auth, secrets,
  SQL injection, logging PII, OWASP Top 10. Dùng khi thêm auth,
  xử lý user input, tạo API endpoints, hoặc features nhạy cảm.
---

# Security Review — issues-sum

Security patterns cho NestJS, align với `.kiro/steering/security.md` và `.kiro/context/conventions.md`.
Full audit: `docs/60-operations/05-security-audit.md` (38 vulnerabilities).

## When to Activate

- Adding authentication/authorization
- Handling user input
- Creating new API endpoints
- Working with secrets
- Storing/transmitting sensitive data
- PR review security check

## Quick Checklist

- [ ] No hardcoded secrets — all from env vars
- [ ] All user input validated with Zod schemas (via NestJS Pipes)
- [ ] Reject unknown fields (Zod strict mode)
- [ ] Parameterized queries (Prisma, no string concatenation)
- [ ] MerchantAuthGuard on all endpoints
- [ ] No PII in logs (passwords, PINs, voucher codes, tokens)
- [ ] Pino redact: `['pin', 'codes', 'codes.*', 'bill_number']`
- [ ] Security headers via helmet
- [ ] Rate limiting via @nestjs/throttler + Redis
- [ ] crypto.randomUUID() for request IDs (not md5/uniqid)

## 1. Secrets Management

```typescript
// ❌ CRITICAL
const apiKey = 'sk_live_abc123xyz';

// ✅ ALWAYS
const apiKey = process.env.API_KEY;
if (!apiKey) throw new Error('API_KEY not configured');
```

## 2. Input Validation (NestJS)

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

// Global pipe
app.useGlobalPipes(new ValidationPipe({
  whitelist: true,
  forbidNonWhitelisted: true,
  transform: true,
}));
```

## 3. SQL Injection Prevention

```typescript
// ❌ DANGEROUS
const query = `SELECT * FROM users WHERE email = '${userEmail}'`;

// ✅ Prisma parameterized
const user = await prisma.user.findFirst({ where: { email: userEmail } });

// ✅ Query builder
const users = await this.repo
  .createQueryBuilder('user')
  .where('user.email = :email', { email: userEmail })
  .getMany();
```

## 4. Authentication & Authorization

```typescript
// Guards on protected endpoints
@UseGuards(JwtAuthGuard, RolesGuard)
@Roles('ADMIN', 'OPERATOR')
@Delete(':id')
async delete(@Param('id') id: string) { }
```

Rules:
- JWT validation on every protected endpoint
- Role-based access at controller/guard level
- Never trust client-supplied role claims
- Use NestJS guards, not scattered auth checks in services

## 5. Logging Security (P1)

```typescript
// ❌ NEVER
logger.info('User login', { email: user.email, password: user.password });
logger.info('Auth', { token: req.headers.authorization });

// ✅ ALWAYS
logger.info('User login', { user_id: user.id, email: maskEmail(user.email) });
```

Never log: passwords, tokens, credit cards, PII (email, phone, address), secret keys.

## 6. Security Headers

```typescript
app.use(helmet({
  contentSecurityPolicy: true,
  crossOriginEmbedderPolicy: true,
  hsts: true,
  frameguard: true,
  hidePoweredBy: true,
  noSniff: true,
  xssFilter: true,
}));
```

## 7. Rate Limiting (Redis)

```typescript
// Aggressive on auth endpoints
@Throttle(10, 60) // 10 requests per 60 seconds
@Post('login')
async login() { }
```

## 8. Webhook Security

- Verify signatures on incoming webhooks before processing
- Allowlist outbound integration targets
- Never trust external callback payloads without validation

## 9. File Upload

- Validate file type (whitelist)
- Enforce size limits
- Sanitize filenames
- Store outside webroot
- Generate random filenames

## OWASP Top 10 Quick Reference

| # | Threat | Mitigation |
|---|--------|-----------|
| A01 | Broken Access Control | RBAC, guards, resource ownership checks |
| A02 | Cryptographic Failures | HTTPS, bcrypt passwords, encrypt sensitive data |
| A03 | Injection | Parameterized queries, validate input |
| A04 | Insecure Design | Security in S3 design phase |
| A05 | Security Misconfiguration | Secure defaults, no debug in prod |
| A06 | Vulnerable Components | npm audit, Trivy scan in CI |
| A07 | Auth Failures | Strong password policy, JWT expiration |
| A08 | Data Integrity | Lock files, verify dependencies |
| A09 | Logging Failures | Structured logging, no PII, monitor security events |
| A10 | SSRF | Validate URLs, whitelist domains |
