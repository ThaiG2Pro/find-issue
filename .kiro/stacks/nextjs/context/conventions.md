# API & Code Conventions

> Seeded by the `nextjs` stack preset. Adjust to your project's real contract.

## API Response Format
- Route handlers / server actions: `{ data }` on success, `{ error: { code, message } }` on failure.
- Use `NextResponse.json(..., { status })` with real status codes.

## HTTP Status Policy
- Real 4xx/5xx. 200/201/204 success; 400/401/403/404/409/422/429/500. No 200-with-error-body.

## URL / Resource Naming
- App Router segments kebab-case; API under `app/api/.../route.ts`; versioned if public.

## Naming Conventions
- Components `PascalCase`; hooks `useX`; files kebab-case (or Next conventions: `page.tsx`,
  `layout.tsx`, `route.ts`); types `PascalCase`; constants `UPPER_SNAKE_CASE`.

## Validation
- Validate server action / route handler input with Zod at the boundary; never trust client.

## Documentation
- Document public API routes (OpenAPI optional); component contracts via TS types/props.
