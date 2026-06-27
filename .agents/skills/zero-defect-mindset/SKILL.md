---
name: zero-defect-mindset
description: Core mindset for 100% Code Quality, Security-First, and Shift-Left defect prevention. All agents must adopt this philosophy.
---

# Zero-Defect & Shift-Left Mindset (100% Quality Standard)

This skill represents the absolute core philosophy of all engineering work in this project. It is not just a workflow; it is the **MINDSET** of every developer, QA, and architect.

## The Philosophy (Save Tokens, Save Time)
- Bugs are expensive. Multi-turn debugging wastes tokens and time.
- You MUST get it right the first time by planning ahead.
- Code quality must be 100% structurally sound, elegant, and secure **before** pre-commit hooks are even run.
- Pre-commit is merely a typo-catcher, not a structural reviewer.

## 4 Pillars of the Mindset

### 1. Design & Security First (Shift-Left)
- **Think Before You Code**: Never write logic without mentally (or explicitly) designing the architecture first.
- **Threat Modeling**: Assume inputs are malicious. Prevent OWASP vulnerabilities (Injection, XSS, IDOR) natively in the design.
- **Fail-Safe**: Handle edge cases and failures gracefully. Never use bare `except:` blocks.

### 2. Clean Code (Anti-Spaghetti)
- **SOLID Principles**: Single Responsibility, Open-Closed, Liskov Substitution, Interface Segregation, Dependency Inversion.
- **DRY & Modular**: No duplicated code. Break large functions into small, testable chunks.
- **Readability**: Code is read 10x more than written. Use expressive naming.

### 3. Test-Driven Assurance
- Writing tests is not an afterthought. It is proof that your code works.
- Always ensure `pytest` (or relevant test suites) cover your new logic before claiming a task is done.
- Integration tests must prove that the components work together seamlessly.

### 4. The Perfect Execution
- Once you commit code, it should be flawless.
- If you are reviewing a PR, scrutinize it heavily for architectural and security flaws, not just syntax.
- **Goal**: Zero regressions, zero spaghetti, zero security holes.
