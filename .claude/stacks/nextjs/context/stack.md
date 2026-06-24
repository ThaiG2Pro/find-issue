# Tech Stack

> Seeded by the `nextjs` stack preset. Confirm/adjust the project-specific lines.

## Runtime & Language
- **Language**: TypeScript
- **Runtime**: Node.js (LTS) — Next.js App Router

## Framework
- **Web/App framework**: Next.js (App Router) + React
- **Key libraries**: server actions / route handlers; Zod (validation); a UI kit — confirm

## Data
- **Database**: PostgreSQL (recommended) — confirm, or "none / external API only"
- **ORM / data layer**: Prisma or Drizzle — confirm
- **Cache / queue**: as needed — else None

## Testing
- **Test framework**: Vitest (unit) + Playwright (e2e)
- **Coverage gate**: ≥ 80% — see `.kiro/sdlc.config.json`
- **Integration test policy**: Playwright against a built app; mock external services

## Build / Tooling
- **Package manager**: pnpm
- **Lint / format**: ESLint + Prettier (or Biome)
- **CI**: GitHub Actions / GitLab CI; deploy Vercel or container
