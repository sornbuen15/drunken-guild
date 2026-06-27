# Release v1.9.0: The Guild Headquarters Architecture

This release establishes the **Centralized Hub Model**, officially transforming the Drunken-Team repository into the Masterbrain/Command Center for all other projects (BETA, SHIELD, etc.).

| Type | Description | Reference |
| :--- | :--- | :--- |
| 🚀 Feature | **Project Registry**: Centralized `.agents/projects.json` for mapping external project workspaces via `src/drunken_team/core/registry.py` | DT-48 |
| 🚀 Feature | **Discord Guild Master**: Mina now parses the target project context dynamically, allowing cross-project commands natively from Discord. | DT-49 |
| 🚀 Feature | **Terminal CWD Routing**: Subprocesses for `agy` now natively inject the project`s Absolute Path as `cwd`, ensuring correct `.agents` loading. | DT-50 |
| 🛠️ Update | **serve_dashboard**: Refactored `load_projects_mapping` to merge directly from the central Project Registry. | DT-49 |
| 🛡️ Stability | Refactored legacy high cyclomatic complexity functions and established Jira zero-defect guidelines. | DT-46 |

> [!NOTE]
> E2E Operations now enforce the **ค.ว.ย. (คิด วิเคราะห์ แยกแยะ)** mindset before execution to ensure precision across multiple environments.


# Release v1.7.0: The AI Guild Platform - Swarm Roles Reorganization

This release fundamentally restructures the AI Agent Swarm architecture into clear Domain-Level Engineering roles and specialized Business Consultants. This prevents context dilution and prepares the foundation for Phase 4 (Auto-Orchestrator Swarm).

| Type | Description | Reference |
| :--- | :--- | :--- |
| 🚀 Feature | Added Engineering Roles (`fullstack-engineer`, `mobile-developer`, `game-developer`) | DAGY-20 |
| 🚀 Feature | Added Business Specialists (`fintech-specialist`, `insurtech-specialist`, `aitech-specialist`) | DAGY-20 |
| 🔄 Update | Transitioned to "Domain-Level Agents + Tech Skills" strategy | DAGY-20 |
| 🗑️ Deprecate | Removed outdated, overlapping agent roles (`frontend-specialist`, `desktop-frontend-dev`) | DAGY-20 |

> [!NOTE]
> All technical customizations are now correctly placed within `.agents/skills/` following the new domain boundaries.
