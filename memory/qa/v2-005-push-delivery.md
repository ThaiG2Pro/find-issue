## 2026-07-08 — v2-005-push-delivery: URL-secret adapter — two-layer URL-leak defense and SSRF smoke pattern

For any adapter whose outbound endpoint URL is itself the credential (Discord/Slack/presigned
webhooks), QA should apply a two-layer URL-leak check: (1) grep error construction code for
str(exc)/repr() that could embed the URL, (2) run smoke tests asserting that the URL string AND
any token substring are absent from ConfigError + DeliveryError messages. A single "URL not in
error" assertion is insufficient — also check the token portion (the substring after the last
slash), since httpx may include only the path in some exception reprs.

Also smoke-test SSRF guard by actually calling load_config with an evil.com URL and asserting
ConfigError is raised AND the URL value is absent from the error message.

## 2026-07-08 — v2-005-push-delivery: pipeline elif branch coverage gap is expected for leaf adapters

When a new delivery adapter is added via an elif branch in pipeline.py, the pipeline-level
tests (which use fixture configs) will not cover the new branch unless a dedicated discord
fixture is added. This is a recurring structural gap for the OSS Pulse pipeline — not a bug.
Pattern: document it in dev-test-report §Known Risks, verify the adapter independently (24
tests), accept the pipeline coverage gap as non-blocking. Recommend a follow-up fixture
rather than holding GO.
