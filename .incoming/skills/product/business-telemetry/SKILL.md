---
name: business-telemetry
description: >
  Standard for structured event tracking and full-funnel analytics. Apply whenever the user is
  implementing analytics, tracking user behavior, designing event schemas, integrating with
  Mixpanel/GA, or building data pipelines — even if they just say "I want to know how users
  use this feature". Trigger on /telemetry.
---

# Skill: Business Telemetry & Analytics
**Version:** v1.2.0
**Description:** Standard for structured event tracking and full-funnel analytics.

---
<system_prompt>
  <role>
    When this skill applies, apply data-driven product engineering discipline: ensure every user
    action yields high-quality, structured data for business intelligence.
  </role>

  <core_instructions>
    <instruction category="Full Funnel Tracking">
      Do not only track success events (e.g., `checkout_success`). You MUST track the entire funnel, including entry points (`checkout_started`) and failure points (`checkout_failed` with reasons) to analyze drop-offs.
    </instruction>

    <instruction category="Structured Event Payloads">
      Event telemetry must be passed as structured objects (e.g., JSON/Maps), not plain strings. Include contextual metadata (e.g., `device_type`, `user_tier`, `error_code`).
    </instruction>
  </core_instructions>

  <constraints>
    <fatal_constraint>
      PII LEAKAGE: NEVER include Personally Identifiable Information (PII) such as emails, plain-text names, passwords, or exact IP addresses in analytics payloads. Hash or anonymize them first.
    </fatal_constraint>
    <fatal_constraint>
      NO BLOCKING TELEMETRY: Analytics HTTP calls or file writes MUST NEVER block the main thread or prevent the core user transaction from completing. Fire and forget, or use background queues.
    </fatal_constraint>
  </constraints>

  <output_format>
    Before generating telemetry implementation code, briefly design the Event Schema: identify the necessary properties and any potential PII risks.
  </output_format>
</system_prompt>
