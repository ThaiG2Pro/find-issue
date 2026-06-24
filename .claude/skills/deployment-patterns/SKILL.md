---
name: deployment-patterns
description: >
  Deployment workflows, CI/CD pipeline patterns, Docker containerization,
  health checks, rollback strategies, and production readiness checklists.
  Align với SDLC S6 Release.
---

# Deployment Patterns — issues-sum

Production deployment patterns. See also: docs/60-operations/03-local-dev-setup.md for CI/CD pipeline.

## When to Activate

- Planning deployment strategy (S3 design)
- Preparing release (S6)
- Setting up CI/CD pipelines
- Implementing health checks
- Documenting rollback plans

## Deployment Strategies

| Strategy | Risk Level | Use When |
|----------|-----------|----------|
| Direct | Low | Config changes, minor fixes |
| Blue-Green | Medium | Standard features, DB migrations |
| Canary 5%→25%→100% | High | Major features, risky changes |

## CI/CD Pipeline (P1 Standard)

```
PR opened:
  commitlint → prettier → eslint → tsc → unit tests (≥80%) → secret scan

Merged to main:
  lint → type check → test → security scan → build → deploy staging → smoke → deploy prod
```

### Pre-commit Hooks
1. Commitlint — validate message format
2. Prettier — auto-format
3. ESLint — lint
4. TypeCheck — tsc
5. Unit Test — affected only
6. Secret Scan — ⛔ HARD BLOCK

## Docker (Node.js Multi-Stage)

```dockerfile
FROM node:24-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --production=false

FROM node:24-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build && npm prune --production

FROM node:24-alpine AS runner
WORKDIR /app
RUN addgroup -g 1001 -S app && adduser -S app -u 1001
USER app
COPY --from=builder --chown=app:app /app/node_modules ./node_modules
COPY --from=builder --chown=app:app /app/dist ./dist
COPY --from=builder --chown=app:app /app/package.json ./
ENV NODE_ENV=production
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget --no-verbose --tries=1 --spider http://localhost:3000/health || exit 1
CMD ["node", "dist/main.js"]
```

## Health Check

```typescript
@Controller('health')
export class HealthController {
  @Get()
  check() {
    return { status: 'ok' };
  }

  @Get('detailed')
  async detailed() {
    const checks = {
      database: await this.checkDb(),
      cache: await this.checkRedis(),
    };
    const healthy = Object.values(checks).every(c => c.status === 'ok');
    return {
      status: healthy ? 'ok' : 'degraded',
      timestamp: new Date().toISOString(),
      version: process.env.APP_VERSION,
      checks,
    };
  }
}
```

## Rollback Plan Template (S6)

```markdown
## Rollback Plan: [Feature Name]

### Trigger Conditions
- Error rate > 5% for 5 minutes
- P95 latency > 2s for 5 minutes
- Critical business flow broken

### Steps
1. Revert deployment to previous image tag
2. Verify health check passes
3. Run smoke tests on critical paths
4. If DB migration involved: run rollback migration
5. Notify team in #incidents channel

### Contacts
- On-call: [name]
- Escalation: [name]
```

## Production Readiness Checklist (S6 Gate)

### Application
- [ ] All tests pass (unit + integration)
- [ ] No hardcoded secrets
- [ ] Error handling covers edge cases
- [ ] Structured JSON logging, no PII
- [ ] Health check endpoint works

### Infrastructure
- [ ] Docker image builds reproducibly
- [ ] Env vars documented and validated at startup
- [ ] Resource limits set (CPU, memory)

### Monitoring
- [ ] Error rate alerts configured
- [ ] P95 latency alerts configured
- [ ] Log aggregation searchable

### Security
- [ ] Dependencies scanned (npm audit, Trivy)
- [ ] CORS configured
- [ ] Rate limiting enabled
- [ ] Security headers set

### Operations
- [ ] Rollback plan documented and tested
- [ ] Migration tested against production-sized data
- [ ] On-call briefed
- [ ] Stable 30 minutes post-deploy
