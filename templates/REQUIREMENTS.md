# Requirements

> Copy this file into your project root as `REQUIREMENTS.md`.
> Fill it out before running any agent session.
> The principal-engineer and `/init-project` use this to generate the prioritized backlog.

---

## Functional Requirements

List features the system must have. Use the MoSCoW format:
- **Must Have** — without this, the product doesn't work or the deadline is missed
- **Should Have** — high value, can survive one cycle without it
- **Could Have** — nice to have, only if Must and Should are complete
- **Will Not Have** — explicitly deferred this phase (prevents scope creep)

### Must Have

| # | Feature | User Story |
|---|---|---|
| F-01 | | As a [user], I want to [action] so that [outcome] |
| F-02 | | |
| F-03 | | |

### Should Have

| # | Feature | User Story |
|---|---|---|
| F-10 | | |
| F-11 | | |

### Could Have

| # | Feature | User Story |
|---|---|---|
| F-20 | | |

### Will Not Have (This Phase)

| # | Feature | Reason Deferred |
|---|---|---|
| F-30 | | |

---

## Non-Functional Requirements

### Performance
<!-- Define measurable thresholds — not aspirations. -->

| Metric | Target | Notes |
|---|---|---|
| Page / screen load time | < ___ ms at P95 | |
| API response time | < ___ ms at P95 | |
| Concurrent users | ___ | |
| Uptime SLA | ___% | |

### Security
<!-- Check all that apply. -->

- [ ] Authentication required (specify method: OAuth 2.0 / JWT / magic link / SSO)
- [ ] Role-based access control (RBAC)
- [ ] Data encrypted at rest
- [ ] Data encrypted in transit (TLS 1.2+ minimum)
- [ ] PII / sensitive data handling (specify fields)
- [ ] Audit logging required
- [ ] Compliance standard: PCI-DSS / HIPAA / SOC 2 / GDPR / CCPA (circle applicable)

### Accessibility
- [ ] WCAG 2.1 Level AA minimum
- [ ] Screen reader support (VoiceOver / TalkBack)
- [ ] Dynamic Type / large text support (mobile)
- [ ] Sufficient color contrast (4.5:1 for body text)

### Scalability
<!-- What load does the system need to handle now and in 12 months? -->

| Dimension | Current | 12-Month Target |
|---|---|---|
| Registered users | | |
| Daily active users | | |
| Transactions / events per day | | |
| Data volume | | |

### Platform & Compatibility

| Platform | Min Version |
|---|---|
| iOS | |
| Android | |
| Web browsers | Chrome ___, Safari ___, Firefox ___ |
| Backend runtime | |

### Offline Support
- [ ] Required — list which features must work offline:
- [ ] Not required

### Localization
- [ ] Single language (specify): ___
- [ ] Multi-language — list languages:

---

## Domain-Specific Requirements
<!-- Fill this section after consulting the domain specialist. -->
<!-- Leave blank and let the specialist populate DOMAIN_BRIEF.md if applicable. -->

### Regulatory / Compliance Requirements
<!-- e.g., KYC required for all users, PCI-DSS SAQ-A scope reduction via tokenization -->

### Domain Data Integrity Rules
<!-- e.g., monetary amounts stored as integer minor units, immutable audit log -->

### Integration Requirements
<!-- External APIs, payment processors, identity providers, third-party services -->

| Integration | Purpose | Notes |
|---|---|---|
| | | |

---

## Definition of Done

A feature is done when:

- [ ] Acceptance criteria from the user story pass
- [ ] Unit tests written and green
- [ ] Integration tests written and green (if applicable)
- [ ] No new lint warnings or type errors introduced
- [ ] Security: no new secrets in code, no new unvalidated inputs at system boundary
- [ ] Accessibility: VoiceOver / TalkBack labels set (mobile), keyboard navigable (web)
- [ ] `/test-report` pre-merge gate passes
- [ ] Conventional commit with type prefix (`feat:`, `fix:`, `chore:`)
- [ ] PR description explains what changed and why
