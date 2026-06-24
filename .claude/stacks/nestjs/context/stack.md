# Tech Stack

> Seeded by the `nestjs` stack preset. Confirm/adjust the project-specific lines.

## Runtime & Language
- **Language**: TypeScript
- **Runtime**: Node.js (LTS — confirm exact version)

## Framework
- **Web/App framework**: NestJS + Fastify adapter
- **Key libraries**: Zod or class-validator (validation), `@nestjs/swagger` (OpenAPI)

## Data
- **Database**: PostgreSQL (recommended) — confirm
- **ORM / data layer**: Prisma (recommended) or TypeORM — confirm
- **Cache / queue**: Redis + BullMQ if needed — else None

## Testing
- **Test framework**: Vitest (or Jest) + Supertest for HTTP
- **Coverage gate**: ≥ 80% lines/branches (see `.kiro/sdlc.config.json`)
- **Integration test policy**: real test DB for repositories; mock external HTTP

## Build / Tooling
- **Package manager**: pnpm (or npm)
- **Lint / format**: ESLint + Prettier (or Biome)
- **CI**: GitLab CI or GitHub Actions
