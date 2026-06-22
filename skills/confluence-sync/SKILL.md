---
name: confluence-sync
description: Synchronizes project documentation files (Architecture, Specs, ADRs, and API docs) to the Confluence Cloud space, maintaining page hierachies. Trigger on `/confluence-sync`, "sync confluence", "publish confluence".
---

# Confluence Documentation Sync Skill

This skill defines the process to parse, structure, and publish workspace documentation to Confluence Cloud space.

## Execution Process

1. **API Bridge Verification**:
   - Ensure the `scripts/confluence_bridge.py` script exists and is executable.
   - Access token must be retrieved from the `JIRA_TOKEN` environment variable.

2. **Generate API Reference**:
   - Run `scripts/openapi_to_markdown.py` to parse the OpenAPI JSON specification (`doc/openapi.json`) and generate a clean Markdown file (`doc/openapi.md`).

3. **Publish Pages in Hierarchy**:
   - **Root Level Pages**:
     - Push `PROJECT_SPEC.md` -> Title: `Project Specification`
     - Push `ARCHITECTURE.md` -> Title: `Architecture Guide`
     - Push `POLICY.md` -> Title: `Security & Integration Policy`
     - Push `doc/openapi.md` -> Title: `API Reference`
   - **Parent Grouping Page**:
     - Create/Update parent page `Architecture Decision Records (ADRs)` under root.
     - Retrieve its numeric `page_id` from the return value.
   - **Child Pages (ADRs)**:
     - Push `ADR-001-autonomous-action-authorization.md` -> Title: `ADR-001: Autonomous Action Authorization` under the parent page ID.
     - Push `ADR-002-websocket-voice-confirmation.md` -> Title: `ADR-002: WebSocket Voice Confirmation` under the parent page ID.

4. **Verify & Document Results**:
   - Compile all created/updated Confluence page IDs and output a clean table summarizing the synchronized documentation.
