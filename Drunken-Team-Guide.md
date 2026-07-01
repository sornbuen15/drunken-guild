# 🍻 Drunken Team: The Ultimate AI Guild Guide

คู่มือฉบับนี้คือ **Single Source of Truth** สำหรับทั้งทีมนักพัฒนา (Devs) และ AI Agents ประจำโปรเจกต์ (Guild NPCs) โดยรวบรวมกติกาการทำงาน, โครงสร้างสถาปัตยกรรม, กฎ Permission Tiers, และ Workflow ต่างๆ เข้าไว้ด้วยกันทั้งหมด

*(Note: เอกสารนี้เป็น Meta-Documentation สำหรับอธิบาย "วิธีทำงาน" ใน Guild หากต้องการอ่านสเปกฟีเจอร์ของแอปพลิเคชันหรือ System Design กรุณาอ้างอิงจาก `PROJECT_SPEC.md` และ `DESIGN.md`)*

---

## 🏗️ 1. Architecture: The Centralized Hub Model
Drunken-Team (หรือ **"Aiขี้เมา"**) ทำหน้าที่เป็น "Guild Headquarters" หรือศูนย์บัญชาการหลักสำหรับ Agents ทั้งหมด

### 1.1 Core Components
* **Project Registry (`src/core/registry.py`):**
  แหล่งเก็บข้อมูล (Single Source of Truth) สำหรับการอ้างอิงตำแหน่งของโปรเจกต์อื่นๆ ทำให้ AI สามารถกระโดดข้ามไปจัดการหลายโปรเจกต์ได้โดยไม่หลงโฟลเดอร์
* **The Discord Guild Master (`src/service/discord_listener.py`):**
  ด่านหน้า (Frontend) ที่คอยรับคำสั่งภาษาธรรมชาติจาก Boss โดยมี **Mina (The AI Hostess)** ทำหน้าที่ Router สกัดเจตนา และเปิด Subprocess สร้าง Agent ไปทำงานในโปรเจกต์ที่ถูกต้อง
* **The Dashboard Transceiver (`src/route/serve_dashboard.py`):**
  หน้าต่างแสดงผล GUI (JRPG-tavern-themed) สำหรับให้มนุษย์ดูสถานะของ Guild และ Agents ที่กำลังวิ่งอยู่

---

## 🛡️ 2. AI Core Directives: Permission Tiers
เพื่อระบบที่เป็นอัตโนมัติ (Zero Friction Automation) AI ต้องยึดหลัก Permission Tiers อย่างเคร่งครัด:

* **🟢 Tier 0: Zero Friction (ทำงานได้ทันที)**
  - อ่าน/เขียนโค้ดภายในโปรเจกต์ได้อิสระ
  - รัน Python ผ่าน `uv run` (ห้ามใช้ `python` เปล่าๆ ออกไปยุ่งกับ OS)
  - ห้ามสะกิด Global Keychain (1Password) โดยเด็ดขาด ต้องแยก Environment
* **🟡 Tier 1: OS / App Consent (ขออนุญาตครั้งแรก)**
  - การเข้าถึงกล้อง/ไมค์/โฟลเดอร์พิเศษ AI ต้องเตือนมนุษย์ก่อนว่าจะมี Pop-up OS เด้ง
* **🟠 Tier 2: Team Protocol (Destructive Actions)**
  - คำสั่งทำลายล้าง (`rm -rf`, `drop db`) **ห้ามทำทันที**
  - ต้องลิสต์เป็นตาราง และใช้สคริปต์ `ask_boss.py` เพื่อรอให้ Boss กด 👍 / 👎 บน Discord
* **🔴 Tier 3: OS Elevation (หวงห้ามเด็ดขาด)**
  - คำสั่ง `sudo` ห้าม AI รันเด็ดขาด ให้เขียนสคริปต์แยกแล้วให้มนุษย์ไปรันเอง

---

## 🗺️ 3. Software Development Workflow (SDLC)
เราใช้ระบบ Agentic SDLC ขั้นสูง โดยยึดหลัก SSOT สองจุด:

### 3.1 Task Management (Jira is SSOT)
- งานทั้งหมด (Intake, Refinement) ต้องวิ่งผ่าน Jira Board เท่านั้น (Backlog -> To Do -> In Progress -> Done)
- ห้ามใช้ Markdown ธรรมดาเก็บ Task
- AI ต้องใช้ `scripts/jira_bridge.py` ในการดึงและอัปเดตงานเสมอ

### 3.2 Documentation (Git is SSOT)
- เอกสาร Technical ให้เขียนเป็น Markdown ใน Git Repo เท่านั้น (Docs-as-Code)
- เมื่อ Merge เข้า `main` แล้ว จึงค่อยใช้ `/confluence-sync` ดันเอกสารขึ้น Confluence

### 3.3 Git Protocol & PR Gates
1. สร้าง Feature Branch เสมอ (ห้ามทำลง `main`)
2. เมื่อเสร็จ เปิด Pull Request (PR)
3. **Merge Authorization:** AI จะ Merge โค้ดได้ ก็ต่อเมื่อเรียก `ask_boss.py` ขออนุญาต Boss ผ่าน Discord และได้รับการกด 👍 เท่านั้น!

---

## 🚀 4. How to Execute the Workflow (Commands)
สำหรับ Dev และ Tech Lead นี่คือคำสั่งหลักสำหรับสั่งงาน Agent:
- `/refine`: ให้ AI ช่วยคัดกรอง Backlog และเตรียมงานเข้า To Do
- `/next-task`: สั่งให้ AI หยิบงานชิ้นต่อไปใน To Do มาประเมิน (Execution Plan) ก่อนเริ่มเขียนโค้ด
- `/audit`: ตรวจสอบ Code Health, หนี้ทางเทคนิค, และ Security
- `/confluence-sync`: ซิงค์เอกสาร `.md` ทะลุขึ้น Confluence

---

## 💻 5. Installation & Setup
1. **Pre-requisites:** Python 3.8+, `uv` (Package Manager), และ Git
2. **Setup Env:** ก๊อปปี้ `sandbox.env.template` (ถ้ามี) ไปเป็น `.env` และตั้งค่า Discord Token / Jira Token
3. **Running the Guild:**
   - รันบอท: `uv run python src/service/discord_listener.py`
   - รันแดชบอร์ด: เปิด `dashboard/index.html` เพื่อดูสถานะ
