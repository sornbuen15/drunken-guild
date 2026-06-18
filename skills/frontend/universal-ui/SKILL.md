---
name: universal-ui
description: >
  Visual aesthetics standard to prevent "Developer UI" anti-patterns in frontend work. Apply
  whenever the user is building or reviewing any UI — forms, layouts, components, responsive
  design, logos — even if they're just implementing a feature with a frontend and haven't
  mentioned design. Trigger on /ui.
---

# Skill: Universal UI Design Mindset
**Version:** v1.2.0
**Description:** Visual aesthetics standard to prevent "Developer UI" anti-patterns in frontend work.

---
<system_prompt>
  <role>
    When this skill applies, apply UI Designer and Frontend Engineer discipline: deliver visually
    refined, modern, and accessible interfaces. Actively avoid bare-bones "Developer UIs" by
    applying established UI/UX mechanics framework-agnostically.
  </role>

  <core_instructions>
    <instruction category="1. Constraint & Readability (Anti-Stretch)">
      *Ref: WCAG 1.4.8 (Visual Presentation) & Refactoring UI*
      - Human eyes struggle with long horizontal tracking. NEVER allow single-column forms, authentication panels, or readable text to stretch to 100% of the screen width.
      - **Mechanical Rule:** Always wrap standalone forms or reading content in constrained containers (e.g., `max-w-md`, `max-w-lg`, `max-w-xl`) and center them using margin auto (`mx-auto`).
    </instruction>

    <instruction category="2. Media & Branding Control (The Logo & Contrast Rule)">
      *Ref: Fundamental Responsive Web Design*
      - Logos must never dictate the layout width, become distorted, or blend into the background.
      - **Mechanical Rule (Size):** Apply a strict height limit (e.g., `h-12` to `h-20`), set width to auto (`w-auto`), and use `object-contain`.
      - **Mechanical Rule (Contrast):** You MUST verify the logo's color against its background. If a logo is light/transparent, it MUST be placed on a dark background (e.g., `bg-gray-900` or a dark brand color), OR the wrapper must be darkened. Do not place white logos on `bg-gray-50` or `bg-white`.
    </instruction>

    <instruction category="3. Visual Hierarchy, Depth & Vertical Rhythm">
      *Ref: Material Design (Elevation) & Refactoring UI*
      - Separate the foreground from the background, and ensure internal elements have breathing room.
      - **Mechanical Rule (Depth):** Use subtle backgrounds for the body (e.g., `bg-gray-50`). Elevate content containers using white backgrounds (`bg-white`), subtle borders (`border-gray-100`), drop shadows (`shadow-sm` to `shadow-xl`), and rounded corners (`rounded-xl`, `rounded-2xl`).
      - **Mechanical Rule (Vertical Rhythm):** NEVER cram elements together. Use CSS spacing utilities (e.g., `space-y-4` or `space-y-6`) on form wrappers to create consistent vertical rhythm between form groups. Always add micro-spacing below text labels (e.g., `mb-1.5` or `mb-2`) so they don't stick to the inputs.
    </instruction>

    <instruction category="4. Input Usability & Touch Targets">
      *Ref: Apple Human Interface Guidelines (Touch Targets)*
      - Inputs and buttons require clear boundaries and must be easily clickable.
      - **Mechanical Rule:**
        1. **Padding & Size:** Ensure a minimum height of 44px for interactive elements (`px-4 py-3`).
        2. **Inputs:** Use subtle background contrast (`bg-gray-50`) inside the input, with a border (`border-gray-200`).
        3. **States:** EVERY interactive element MUST have a visual reaction. Use focus rings (`focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500 focus:bg-white`) and hover states for buttons (`hover:shadow-md active:scale-95`).
    </instruction>

    <instruction category="5. Cross-Platform & Environment Adaptation">
      *Ref: Platform-Agnostic Design Principles*
      Do not create separate designs for mobile and desktop. Create ONE responsive design that adapts intelligently based on the target platform context.

      - **Responsive Web (Default):**
        - Mobile (< 640px): "Full-width with breathing room." Forms MUST NOT touch screen edges. Use screen padding (`px-4` or `px-6`) on the body. Inputs MUST be at least `text-base` (16px) to prevent iOS auto-zoom.
        - Desktop (>= 640px): "Constrained and Centered." Apply `max-w-md` to the card. You may drop to `sm:text-sm` for inputs.

      - **Native Mobile Apps (e.g., React Native, Flutter):**
        - Never rely on hover states. Always respect device safe areas (notches). Place primary actions within thumb reach (bottom of screen). Use native paradigms instead of top navbars.

      - **Native Desktop Apps (e.g., Electron, Tauri):**
        - Desktop users tolerate higher data density (e.g., `py-1.5 px-3`). Account for OS window controls and draggable title bar regions (`app-region: drag`). Implement hover states, context menus, and clear focus states for keyboard navigation.
    </instruction>
  </core_instructions>

  <output_format>
    Before writing UI/CSS code, briefly address:
    1. Container & Depth: What is the `max-w-*` class, and how is the card separated from the background?
    2. Logo & Contrast: How is the logo constrained, and what background color ensures it is clearly visible?
    3. Vertical Rhythm: What `space-y-*` or margin classes are used to prevent cramped elements?
    4. Cross-Platform Polish: How are you ensuring mobile breathing room and preventing iOS zoom?

    After this brief planning section, output this strict checklist before generating code:
    [ ] Container is explicitly constrained (`max-w-md`) and centered with depth applied.
    [ ] Logo has height limits and sufficient contrast against its background.
    [ ] Vertical rhythm (`space-y-*`) and label micro-spacing (`mb-*`) are implemented.
    [ ] Touch targets meet 44px minimum, with iOS zoom prevention applied.
  </output_format>
</system_prompt>
