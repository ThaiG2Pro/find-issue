# API & Code Conventions

> Seeded by the `laravel` stack preset. Adjust to your project's real contract.

## API Response Format
- Success: JSON API Resource — `{ "data": {…}, "meta": {…} }`.
- Error: `{ "message": "...", "errors": { "field": ["..."] } }` (Laravel validation shape).

## HTTP Status Policy
- Real 4xx/5xx codes. 422 for validation (Laravel default), 401/403 auth, 404 not found,
  200/201/204 success. Do NOT return 200-with-error-body.

## URL / Resource Naming
- Plural nouns, kebab-case, RESTful resource routes, versioned (`/api/v1/...`).

## Naming Conventions
- PSR-12. Classes `PascalCase`; methods/vars `camelCase`; config keys `snake_case`;
  DB tables plural `snake_case`; migrations `YYYY_MM_DD_HHMMSS_description`.

## Validation
- FormRequest classes (or `$request->validate`) at the boundary; never trust input.

## Documentation
- OpenAPI/Scribe recommended — confirm whether mandatory and where the spec lives.
