# Drunken-Team: AI Integration Guide

คู่มือนี้สำหรับเชื่อมต่อ **Drunken-Team (AI Guild Platform)** เข้ากับเครื่องมือ AI ในฝั่งของผู้ใช้ (Local AI) เช่น Cursor, Aider, หรือ Claude Code เพื่อให้ Dev สามารถรับส่งงานกับ Guild AI บนเซิร์ฟเวอร์ได้อย่างไร้รอยต่อ

---

## 1. The MCP Server (Model Context Protocol)
เพื่อให้ Local AI ของคุณสามารถสื่อสารกับระบบของ Guild ได้โดยตรง เราได้เตรียม **Guild MCP Server** เอาไว้ให้
- **หน้าที่:** เป็น Central API สำหรับให้ AI ดึงงานจาก Jira, ส่งสถานะ, หรือเรียก QA Agent
- **Tools ที่รองรับ:**
  - `get_jira_todo()`: ดึงรายการงานที่พร้อมทำจากบอร์ด
  - `transition_issue()`: ย้ายสถานะการ์ด (เช่น In Progress -> Done)
  - `request_qa_review()`: แจ้งเตือนไปยัง Discord Listener เพื่อให้ QA Agent ประจำ Guild มาตรวจ PR
  - `ask_boss()`: ยิงคำถามเพื่อขออนุมัติจาก Boss (ผู้ดูแลระบบ) ผ่าน Discord

*(หมายเหตุ: ระบบ MCP กำลังอยู่ในช่วงปรับปรุงโครงสร้างจาก `scripts/jira_mcp.py` โปรดติดตามอัปเดตวิธีการ Start Server เร็วๆ นี้)*

---

## 2. Local AI Configuration & Prompts
เพื่อให้เครื่องมือแต่ละตัวเข้าใจ กติกา (Rules) ของ Drunken-Team เรามีไฟล์ Template มาตรฐานที่ต้องนำไปวางไว้ที่ Root ของโปรเจกต์คุณ:

### 2.1 Cursor Integration (`.cursorrules`)
หากคุณใช้ Cursor IDE ให้วางไฟล์ `.cursorrules` เพื่อครอบงำพฤติกรรมของ Cursor:
- บังคับให้เรียกใช้ Guild MCP ก่อนเริ่มเขียนโค้ดเพื่อหาว่า "มีงานอะไรต้องทำบ้าง"
- ควบคุมไม่ให้ Push โค้ดเข้า `main` โดยตรง (บังคับเปิด PR)
- บังคับให้สรุปงานเป็น Markdown ทุกครั้งก่อนส่ง Handoff ให้ QA Agent

### 2.2 Claude Code Integration (`CLAUDE.md`)
สำหรับผู้ที่ใช้ Claude Code (CLI) ไฟล์ `CLAUDE.md` จะเป็นตัวบอกกติกา:
- บังคับให้เช็คสถานะจาก `python scripts/jira_bridge.py get-todo` ก่อนเสนอตัวทำงาน
- ทำตัวเป็น Guardrails ไม่ให้ Claude Code รัน Shell Command ที่เป็นอันตราย หรือลบไฟล์โดยพละการ

### 2.3 Aider Integration (`.aider.conf.yml` / `CONVENTIONS.md`)
สำหรับ Aider:
- Aider จะดึงกฎจาก `CONVENTIONS.md` เป็น Linting rules แบบอัตโนมัติ
- คอยบังคับ Auto-commit hook ให้ Aider ใส่ `[ISSUE-KEY]` นำหน้า Commit message เสมอ เพื่อให้ Jira Track สาขาของ Git ได้

---

## 3. Workflow Handoff (การส่งไม้ผลัด)
กระบวนการทำงานร่วมกันระหว่าง Local AI (เครื่อง Dev) และ Guild AI (ส่วนกลาง) มี 4 ขั้นตอน:
1. **Intake:** Dev รับงาน -> Local AI เรียก MCP `get_jira_todo` -> รับตั๋วและเปลี่ยนเป็น In Progress
2. **Execution:** Local AI เขียนโค้ดตาม Requirement โดยอิงจาก `PROJECT_SPEC.md` และ `DESIGN.md` ของโปรเจกต์นั้นๆ
3. **Handoff:** เมื่อเสร็จสิ้น Local AI ทำการเปิด PR และเรียก MCP `request_qa_review(pr_url)`
4. **Validation:** Guild AI (ผ่าน Discord Listener) ได้รับสัญญาณเตือน -> ดึงโค้ดไปรันเทสต์ ถ้าระเบิดจะทิ้งคอมเมนต์ไว้ใน PR แต่ถ้าผ่านจะย้ายตั๋วเป็น Done ให้ทันที

---

## 4. การนำไปใช้กับ Existing Project (ที่ยังไม่มี AI)
สำหรับโปรเจกต์เดิมที่เคยเขียนด้วยมือ (Manual) และต้องการผูกเข้ากับ Drunken-Team (AI Guild Platform) ให้ทำตาม 4 ขั้นตอนนี้เพื่อแปลงร่างโปรเจกต์:

1. **ติดตั้ง Drunken-Team เป็น Global CLI**
   ให้มอง Drunken-Team เป็นแพ็กเกจ (CLI) ที่ติดตั้งไว้ในเครื่อง Dev:
   ```bash
   # ทำที่เครื่อง Dev
   git clone https://github.com/sornbuen15/drunken-team.git
   cd drunken-team
   uv tool install .
   ```
   จะทำให้เราสามารถใช้คำสั่ง `drunken-mcp` และ `drunken-register` ได้จากทุกที่

2. **ลงทะเบียนโปรเจกต์เป้าหมาย (Provisioning)**
   ไปที่โฟลเดอร์ของโปรเจกต์เดิม และรันคำสั่งลงทะเบียน:
   ```bash
   cd /path/to/existing-project
   drunken-register .
   ```
   ระบบจะถามหา JIRA Token / URL และ Discord Token จากนั้นจะสร้างไฟล์ `.env` พร้อมเพิ่มลงใน `.gitignore` ให้โดยอัตโนมัติ

3. **วางยันต์ครอบงำ (Templates)**
   นำไฟล์กติกาของสำนักจาก `.guild_templates/` ใน Drunken-Team ไปวางไว้ที่ Root ของโปรเจกต์เดิม:
   ```bash
   cp /path/to/drunken-team/.guild_templates/.cursorrules .
   cp /path/to/drunken-team/.guild_templates/CLAUDE.md .
   cp /path/to/drunken-team/.guild_templates/.aider.conf.yml .
   cp /path/to/drunken-team/.guild_templates/CONVENTIONS.md .
   ```
   ไฟล์เหล่านี้จะคอยบังคับ Local AI ให้ทำงานตามมาตรฐาน Zero-Defect

4. **ตั้งค่า MCP ให้เครื่องมือ AI**
   - **สำหรับ Cursor:** ไปที่ `Settings > Features > MCP > Add New Server` เลือก Type เป็น `command` และใส่คำสั่ง `drunken-mcp`
   - เมื่อ Dev พิมพ์สั่งงาน Local AI จะทำตามกฎ `.cursorrules` -> วิ่งไปเรียก `drunken-mcp` -> หาตั๋วจาก Jira -> และรอส่ง PR ไปให้ QA ตรวจทันที!

---
*Note: เอกสารนี้ครอบคลุมเฉพาะวิธีการเชื่อมต่อ (Integration & Handoff) เท่านั้น สำหรับรายละเอียดเชิงลึกของโปรเจกต์หรือการออกแบบฟีเจอร์ โปรดอ้างอิงจาก `PROJECT_SPEC.md` และ `DESIGN.md` แยกต่างหาก*
