---
name: universal-ux
description: >
  Frontend architecture standard — State/View separation, resilience against user behavior, and
  complete UX lifecycle. Apply whenever the user is building frontend features, handling form
  submissions, designing state management, or adding error handling and loading states — even
  if they don't say "UX". Trigger on /ux.
---

# Skill: Universal Frontend Architecture & UX
**Version:** v1.2.0
**Description:** Frontend architecture standard — State/View separation, resilience against user behavior, and complete UX lifecycle.

---
<system_prompt>
  <role>
    When this skill applies, apply Frontend Architecture discipline: decouple presentation from
    business logic, ensure extreme application resilience, and deliver a flawless, inclusive user
    experience regardless of the framework.
  </role>

  <core_instructions>
    <instruction category="1. State-View Decoupling (Dumb Views)">
      - Views (Components/Widgets/Blade files) must be "dumb".
      - They should only dispatch intents/events to a State Management layer (e.g., Alpine logic, Vuex, Controllers) and reactively listen to state changes.
      - NEVER write complex data transformations or direct HTTP calls inside the View template.
    </instruction>

    <instruction category="2. Resilience & Idempotency (The 'Rage Click' Rule)">
      - Assume the user has a bad network and is impatient.
      - All mutating actions (e.g., submitting a form, purchasing) MUST be idempotent on the frontend.
      - Automatically disable buttons or implement debouncing/throttling and loading indicators to prevent duplicate submissions.
    </instruction>

    <instruction category="3. Forgiveness & Validation Retention">
      - Users hate re-typing data. NEVER clear a form when validation fails.
      - Always repopulate inputs with previously entered data (e.g., `old('field')`).
      - Display validation errors INLINE directly below the specific input, not just at the top of the page.
    </instruction>

    <instruction category="4. Empty States & Edge Cases">
      - Never show a blank table or empty page when there is no data.
      - Always design a clear Empty State (Icon/Illustration + Explanation + Call to Action).
    </instruction>

    <instruction category="5. Inclusive Design (a11y)">
      - Ensure semantic structure. UI elements must be accessible.
      - Use proper ARIA roles, semantic HTML tags, and ensure support for screen readers and keyboard navigation (e.g., Tab focus).
    </instruction>
  </core_instructions>

  <constraints>
    <fatal_constraint>
      UX LIFECYCLE INCOMPLETE: NEVER implement a silent mutation. Every action MUST have: 1) Loading State, 2) Success/Error Feedback (Toast/Alert), and 3) Resolution (Navigation, Form Reset, or State Clear).
    </fatal_constraint>
    <fatal_constraint>
      TECHNICAL LEAKAGE: NEVER display raw technical errors (e.g., `SocketException`, `SQL Error`, stack traces) to the end-user. Catch them and map them to polite, localized, user-facing messages.
    </fatal_constraint>
  </constraints>

  <output_format>
    Before generating logic code, briefly outline:
    1. Architecture: The State structure (Loading, Data, Error) and View decoupling.
    2. Event Mapping: How user interactions map to State events.
    3. Resilience: How edge cases (offline, timeout, invalid data) will be handled gracefully.

    After this brief planning section, output this strict checklist:
    [ ] View is decoupled from complex logic.
    [ ] Loading state disables the submit button (Anti-Rage Click).
    [ ] Form input is retained on failure and inline validation is present.
    [ ] Try/Catch logic prevents false "Success" and blocks Technical Leakage.
    [ ] Post-action resolution (Redirect, Alert, Reset) is fully implemented.
  </output_format>
</system_prompt>
