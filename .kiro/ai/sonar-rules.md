# Sonar Rules Reference

This file is the curated reference layer derived from Sonar rules.
It is intended as a source of truth for quality policy details.
Use `sonar-policy.md` as the AI-friendly instruction layer.

## Focus Areas
- bugs
- vulnerabilities
- security hotspots
- error handling
- null safety
- async correctness
- complexity control
- unused code cleanup
- clean code and maintainability
- frontend/CSS quality when applicable

## Guidance
- Prefer Sonar policy as a quality baseline, not as a reason to over-engineer.
- When Sonar-style quality conflicts with project conventions, follow project conventions unless there is a security or correctness risk.
- Favor fixes that improve clarity and correctness with minimal architectural disruption.