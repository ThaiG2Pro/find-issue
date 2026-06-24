# Tech Stack

> Seeded by the `laravel` stack preset. Confirm/adjust the project-specific lines.

## Runtime & Language
- **Language**: PHP (8.2+ recommended — confirm)
- **Runtime**: PHP-FPM

## Framework
- **Web/App framework**: Laravel
- **Key libraries**: Laravel Sanctum/Passport (auth) if needed; Laravel Octane optional

## Data
- **Database**: MySQL or PostgreSQL — confirm
- **ORM / data layer**: Eloquent (+ migrations)
- **Cache / queue**: Redis + Laravel Queue if needed — else None

## Testing
- **Test framework**: PHPUnit or Pest
- **Coverage gate**: ≥ 80% (pcov/xdebug) — see `.kiro/sdlc.config.json`
- **Integration test policy**: `RefreshDatabase` against a test DB; mock external HTTP

## Build / Tooling
- **Package manager**: Composer
- **Lint / format**: Laravel Pint (PSR-12)
- **CI**: GitLab CI or GitHub Actions
