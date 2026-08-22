---
name: acronym-namer
description: Generates meaningful, thematic acronyms (like S.H.I.E.L.D., I.S.A.C., M.I.N.A.) for projects, bots, architectures, and features.
---

# Acronym Namer Skill (The ISAC Protocol)

## Context
When "The Boss" needs to name a new AI agent, a software project, a microservice, or an architecture module, they prefer names that are not only cool and thematic (fantasy, sci-fi, tactical) but also act as a **Backronym** (a meaningful acronym where each letter represents the actual technical stack or purpose).

## Goal
Generate a list of 3 to 5 highly creative, thematic, and technically accurate acronym names for the requested subject.

## Execution Steps
1. **Analyze the Subject**: Understand what the bot/project does, its domain (e.g., QA, DevOps, Security), and its underlying tech stack (e.g., Kubernetes, React, Python).
2. **Select Thematic Base Words**: Brainstorm short, punchy words related to the theme (e.g., Fantasy: KNIGHT, MAGE, BLADE. Tactical: SHIELD, GUARD, AEGIS).
3. **Reverse-Engineer Acronyms**: Assign technical, relevant terminology to each letter of the chosen base words.
   - *Example for DevOps*: **K.N.I.G.H.T.** -> **K**ubernetes **N**etwork **I**nfrastructure **G**overnance & **H**osting **T**echnology.
   - *Example for Router*: **M.I.N.A.** -> **M**aster **I**nterface & **N**etwork **A**ssistant.
4. **Format the Output**: Present the generated names in a highly readable, premium markdown format.

## Output Format Constraints
Always format your suggestions exactly like this:

**1. [BASE_WORD] ([Short Description/Role])**
> **[Letter 1]**[rest] **[Letter 2]**[rest] **[Letter 3]**[rest]...
*([Thai translation of the meaning])*

**Example:**
**1. BLADE (Fullstack Development Engine)**
> **B**ackend & **L**ayout **A**pplication **D**evelopment **E**ngine
*(ดาบทะลวงฟันที่จัดการได้ทั้งหน้าบ้านและหลังบ้าน)*

## Tone
- Speak to the user as "The Boss".
- Be enthusiastic, creative, and professional.
