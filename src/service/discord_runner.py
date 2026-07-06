import asyncio
import json
import os
import sys
from typing import Any

import discord

from service.discord_utils import (
    extract_clean_response,
    log_activity,
    query_gemini_direct,
)

RAW_LOG_FILE = "agy_discord_raw.log"
file_lock = asyncio.Lock()


class AgentRunner:
    def __init__(self) -> None:
        self.current_process: asyncio.subprocess.Process | None = None
        self.current_status_msg: discord.Message | None = None
        self.is_cancelled: bool = False

    def is_busy(self) -> bool:
        return (
            self.current_process is not None and self.current_process.returncode is None
        )

    async def cancel_current_task(self) -> None:
        if self.is_busy() and self.current_process:
            self.is_cancelled = True
            try:
                self.current_process.terminate()
                await asyncio.sleep(0.5)
                if self.is_busy():
                    self.current_process.kill()
            except Exception:
                pass

    async def _execute_command(
        self,
        cmd_args: list[str],
        agent_name: str,
        env_vars: dict[str, Any] | None,
        cwd: str | None = None,
    ) -> tuple[int | None, Exception | None]:
        env = os.environ.copy()
        if env_vars:
            env.update(env_vars)

        env.pop("SSH_AUTH_SOCK", None)

        import shutil

        if cmd_args and cmd_args[0] == "agy" and shutil.which("uv"):
            cmd_args = ["uv", "run"] + cmd_args

        task_log = f"agy_discord_{agent_name.replace(' ', '_').lower()}_raw.log"

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=env,
                cwd=cwd,
            )
            self.current_process = process

            with open(task_log, "w", encoding="utf-8") as f:
                if process.stdout:
                    while True:
                        line = await process.stdout.readline()
                        if not line:
                            break
                        decoded_line = line.decode("utf-8", errors="replace")
                        sys.stdout.write(decoded_line)
                        sys.stdout.flush()
                        f.write(decoded_line)
                        f.flush()

            await process.wait()
            try:
                if os.path.exists(task_log):
                    async with file_lock:
                        with open(task_log, "r", encoding="utf-8") as tf:
                            log_content = tf.read()
                        with open(RAW_LOG_FILE, "w", encoding="utf-8") as rf:
                            rf.write(log_content)
                    os.remove(task_log)
            except Exception:
                pass
            return self.current_process.returncode, None
        except Exception as e:
            return None, e

    async def _handle_command_error(
        self, e: Exception, agent_name: str, status_msg: discord.Message
    ) -> None:
        async with file_lock:
            with open(RAW_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(f"\nError executing command: {e}\n")
        log_activity("agent", "Agent", f"Failed: {e}")
        await status_msg.edit(
            content=f"⚠️ **Oh no, Boss!** The quest order for **{agent_name}** failed to start:\n`{e}`"
        )
        try:
            await status_msg.clear_reactions()
        except Exception:
            pass

    async def _handle_command_success(
        self,
        channel: discord.abc.Messageable,
        user_mention: str,
        status_msg: discord.Message,
        agent_name: str,
        project_id: str,
    ) -> None:
        clean_resp = ""
        if os.path.exists(RAW_LOG_FILE):
            try:
                async with file_lock:
                    with open(RAW_LOG_FILE, "r", encoding="utf-8") as f:
                        raw_log = f.read()
                clean_resp = extract_clean_response(raw_log)
            except Exception:
                pass

        try:
            await status_msg.clear_reactions()
        except Exception:
            pass

        await status_msg.edit(
            content="🎯 **Quest completed, Boss!**\n🏁 **Status:** Finished! The report is served at your table."
        )

        footer = f"\n\n---\n*Reply to this message to continue working with **{agent_name}** in `{project_id}`*"

        if clean_resp:
            log_activity("agent", "Agent", clean_resp)
            formatted_content = (
                f"🛎️ **Boss! The report is served!** ({user_mention})\n\n{clean_resp}"
            )
            if len(formatted_content) + len(footer) > 1950:
                formatted_content = (
                    formatted_content[: 1950 - len(footer)]
                    + "...\n*(Content too long. Type !detail to upload the full raw log file)*"
                )
            await channel.send(formatted_content + footer)
        else:
            log_activity("agent", "Agent", "Completed.")
            await channel.send(
                f"🛎️ **Boss! The report is served!** ({user_mention})\n🏁 **Status:** Completed. *(Type !detail to check execution logs)*{footer}"
            )

    async def _handle_quest_failure(
        self,
        channel: discord.abc.Messageable,
        user_mention: str,
        command_content: str,
        agent_name: str,
        status_msg: discord.Message,
        project_id: str,
    ) -> None:
        self.current_process = None
        self.current_status_msg = None

        log_content = ""
        try:
            if os.path.exists(RAW_LOG_FILE):
                async with file_lock:
                    with open(RAW_LOG_FILE, "r", encoding="utf-8") as f:
                        log_content = f.read()
        except Exception:
            pass

        instruction = (
            "You are Principal Engineer. Analyze the given execution log and explain WHY it failed. "
            "Provide a short root cause (1-2 sentences). Do not use JSON."
        )

        analysis = "Unknown failure during execution (Log empty)."
        if log_content:
            tail = log_content[-4000:]
            try:
                res = await asyncio.to_thread(query_gemini_direct, tail, instruction)
                if res:
                    analysis = res
            except Exception as e:
                analysis = f"Failed to analyze log: {e}"

        title = f"Hotfix: {agent_name} repeatedly failed on task"
        desc = f"Task: {command_content}\n\nCause:\n{analysis}"

        ticket_key = "UNKNOWN"
        try:
            jira_script = os.path.join(os.getcwd(), "scripts", "jira_bridge.py")
            proc = await asyncio.create_subprocess_exec(
                "python",
                jira_script,
                "create",
                title,
                desc,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if stdout:
                out_json = json.loads(stdout.decode().strip())
                ticket_key = out_json.get("key", "UNKNOWN")
                if ticket_key != "UNKNOWN":
                    await asyncio.create_subprocess_exec(
                        "python", jira_script, "transition", ticket_key, "In Progress"
                    )
        except Exception as e:
            print(f"Failed to create Hotfix ticket: {e}", file=sys.stderr)

        await status_msg.edit(content="🚨 **Task Failed!**")
        footer = f"\n\n---\n*Reply to this message to continue working with **{agent_name}** in `{project_id}`*"
        await channel.send(
            content=(
                f"🚨 **Emergency Report, {user_mention}!**\n"
                f"**{agent_name}** wiped in the dungeon (Quest Failed).\n"
                f"**Agy:** I've stopped the task and created a Hotfix ticket **{ticket_key}** in 'In Progress' for you!\n"
                f"**Root Cause Analysis:**\n{analysis}{footer}"
            )
        )
        log_activity("agent", "Agy", f"Created Hotfix {ticket_key} for {agent_name}")

    async def run_command_async(
        self,
        channel: discord.abc.Messageable,
        user_mention: str,
        command_content: str,
        cmd_args: list[str],
        agent_name: str,
        env_vars: dict[str, Any] | None = None,
        cwd: str | None = None,
        project_id: str = "drunken-team",
    ) -> None:
        if not cmd_args or cmd_args[0] not in ("agy",):
            return

        status_msg = await channel.send(
            f"🎯 **Quest order received, Boss!** 🚀\n"
            f"Agy has dispatched the quest order to **{agent_name}** in the backroom office.\n"
            f"I'll bring the report straight to your table once completed!\n"
            f"⏳ **Status:** Processing behind the scenes... *(You can click ❌ to cancel the order anytime, Boss)*"
        )
        try:
            await status_msg.add_reaction("❌")
        except Exception:
            pass

        self.current_status_msg = status_msg
        self.is_cancelled = False

        _, exc = await self._execute_command(cmd_args, agent_name, env_vars, cwd)

        self.current_process = None
        self.current_status_msg = None

        if self.is_cancelled:
            log_activity("agent", "Agent", "Task cancelled by user.")
            await status_msg.edit(
                content="🛑 **Order cancelled, Boss!**\n🏁 **Status:** Recalled by the Guild Master."
            )
            try:
                await status_msg.clear_reactions()
            except Exception:
                pass
            self.is_cancelled = False
            return

        if exc:
            await self._handle_quest_failure(
                channel,
                user_mention,
                command_content,
                agent_name,
                status_msg,
                project_id,
            )
            return

        await self._handle_command_success(
            channel, user_mention, status_msg, agent_name, project_id
        )
