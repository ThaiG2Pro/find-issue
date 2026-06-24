# Sonar Policy

## Bug Prevention
- Remove unused code, variables, imports, and unreachable paths.
- Avoid duplicated conditions and suspicious control flow.
- Use safe defaults and explicit null handling.

## Error Handling
- Use specific exceptions or error types.
- Keep error messages meaningful.
- Preserve context when rethrowing or wrapping errors.

## Async Safety
- Do not leave floating promises.
- Await or handle promise results intentionally.
- Make retries and async jobs safe for repeated execution.

## Complexity Control
- Keep functions and methods focused.
- Avoid deep nesting and excessive branching.
- Extract complex logic into named helpers or services when needed.

## Security Baseline
- Do not hardcode credentials.
- Do not build SQL queries unsafely.
- Validate untrusted input.
- Avoid exposing sensitive internals.