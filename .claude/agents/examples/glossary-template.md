---
name: glossary-template
description: >
  Template for {CHANGE_DIR}/_glossary.md — the shared, append-only domain/technical glossary
  every agent adds to. These definitions are the canonical truth across all phases. cpp-guard
  checks this is a markdown table with >=1 data row (S2) and >=1 row whose Phase is S3 (S3).
  IMPORTANT: keep "Phase" as the LAST column — cpp-guard reads the trailing cell as the phase.
---

# Glossary — {change-name} (ticket {ticket_id})

| Term | Definition | Defined by | AC/BR ref | Phase |
|------|-----------|-----------|-----------|-------|
| {Domain term} | {exact, agreed definition — reused verbatim downstream} | analyst | AC-{ticket}-001 | S2 |
| {Business rule name} | {definition} | analyst | BR-{ticket}-001 | S2 |
| {Architecture pattern / service / lock strategy} | {definition} | architect | ADR-001 | S3 |

<!--
  APPEND a row for every term you define or clarify; never delete a row.
  - Defined by: analyst | architect | developer | qa
  - AC/BR ref: the AC/BR/ADR id this term anchors to, or "—" if none
  - Phase (LAST column, required): S1 | S2 | S3 | S4 | S5 | S6
-->
