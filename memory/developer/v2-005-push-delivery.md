## 2026-07-08 — v2-005-push-delivery: httpx exception ordering — TimeoutException must be caught before RequestError

httpx.TimeoutException is a subclass of httpx.RequestError. In an except chain, catch
TimeoutException first; otherwise the RequestError branch catches it and you emit the
wrong error message. This applies to any httpx-based adapter that distinguishes timeout
from connection errors. Also: str(httpx.RequestError) embeds the request URL — always
compose error messages from type(exc).__name__ (network errors) or response.status_code
(HTTP errors), never from str(exc).

## 2026-07-08 — v2-005-push-delivery: Delivery Protocol is not @runtime_checkable — use duck-type inspection in tests

osspulse.ports.Delivery (and all other Protocol classes in ports.py) lack
@runtime_checkable, so isinstance(obj, Delivery) raises TypeError at runtime.
In tests that verify structural port compliance, use callable(getattr(obj, 'deliver', None))
or inspect the method signature. Don't add @runtime_checkable to ports.py as a workaround —
that's a shared contract file owned by the architect.
