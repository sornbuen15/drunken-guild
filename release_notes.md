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
