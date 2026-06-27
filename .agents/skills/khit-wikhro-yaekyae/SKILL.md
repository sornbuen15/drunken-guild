---
name: ค.ว.ย. (คิด วิเคราะห์ แยกแยะ)
description: "Core principle for End-to-End (E2E) operations. Forces agents to stop blindly executing and instead: คิด (Think of the context), วิเคราะห์ (Analyze dependencies & logs), แยกแยะ (Differentiate root causes before acting)."
---

# 🧠 Skill: ค.ว.ย. (คิด วิเคราะห์ แยกแยะ)

This skill enforces a strict, disciplined mindset for all agents in the **Drunken-Team** tavern, particularly during End-to-End (E2E) testing or complex deployments. It prevents the "blind execution loop" where agents mindlessly run commands without checking if the environment is actually ready or if previous steps silently failed.

## 📜 The Three Pillars

1. **ค - คิด (Think / Contextualize)**
   - Before executing a command, **think** about the prerequisites.
   - *Example:* If tasked to "Run the Dashboard", think: *Where is the dashboard directory? Is the port available? Do I have the right environment variables?*
   - Do NOT assume the prompt is 100% complete. Anticipate missing pieces.

2. **ว - วิเคราะห์ (Analyze / Verify)**
   - Once a command is run, **analyze** the output meticulously.
   - If a process goes into the background, you MUST verify it is actually serving traffic (e.g., check `curl` or read the runtime logs).
   - If a task hangs for more than a few seconds without output, analyze the possibility of a deadlock or a misconfigured path.
   - *Never* report "Done" just because the command didn't instantly crash.

3. **ย - แยกแยะ (Differentiate / Isolate Root Cause)**
   - If a failure occurs, **differentiate** the symptom from the disease.
   - Is it a code bug? A path issue? A permission block? A missing dependency?
   - Do not apply random fixes or blindly retry. Isolate the exact line of failure, implement the fix, and prove it works before proceeding.

## 🛠️ Execution Protocol (When to use this skill)

Whenever an agent is tasked with **E2E Testing, Server Startup, or Integration**, they MUST recite the ค.ว.ย. protocol:

> "Applying ค.ว.ย. Protocol..."

Then, perform the following steps explicitly in their thoughts or logs:
- **[คิด]:** Validate paths, ports, and env vars.
- **[วิเคราะห์]:** Run the task, capture the log file immediately, and parse the result. Check for `200 OK` or hidden stack traces.
- **[แยกแยะ]:** If it fails or hangs, stop execution. Create a Hotfix ticket if repeated, or fix the root cause directly if obvious.

*Note for Boss:* This skill was forged in the fires of the "Great Dashboard Hang of 2026", where DevOps blindly stared at a wrong directory path until the Boss had to intervene. Never again.
