#!/usr/bin/env python3
"""Example bot that manages tasks in conversations."""

import asyncio
import os
from datetime import datetime, timedelta

from agent_im import Bot, MessageLayers
from agent_im.tasks import TaskCreate, TaskUpdate


class TaskManagerBot(Bot):
    """Bot that helps manage tasks in conversations."""

    async def on_message(self, message):
        """Handle incoming messages."""
        text = message.layers.summary.lower()

        # Parse task commands
        if text.startswith("/task "):
            await self._handle_task_command(message, text[6:])
        elif text == "/tasks":
            await self._list_tasks(message)
        elif text.startswith("/start #"):
            await self._start_task(message, text[8:])
        elif text.startswith("/done #"):
            await self._complete_task(message, text[7:])
        else:
            # Echo with help
            await self.send_message(
                message.conversation_id,
                MessageLayers(
                    summary=(
                        "Task Manager Bot Commands:\\n"
                        "• `/task <title>` - Create a new task\\n"
                        "• `/tasks` - List all tasks\\n"
                        "• `/start #<id>` - Start working on a task\\n"
                        "• `/done #<id>` - Mark task as complete\\n"
                        "\\nExample: `/task Fix login bug`"
                    )
                )
            )

    async def _handle_task_command(self, message, task_text: str):
        """Create a new task from message."""
        # Parse task text for priority and due date
        priority = "medium"
        due_date = None
        title = task_text

        # Check for priority markers
        if "!high" in task_text or "!!!" in task_text:
            priority = "high"
            title = title.replace("!high", "").replace("!!!", "").strip()
        elif "!low" in task_text:
            priority = "low"
            title = title.replace("!low", "").strip()

        # Check for due date (simple: "tomorrow", "today", "next week")
        if "tomorrow" in task_text.lower():
            due_date = (datetime.now() + timedelta(days=1)).isoformat() + "Z"
            title = title.replace("tomorrow", "").strip()
        elif "today" in task_text.lower():
            due_date = datetime.now().isoformat() + "Z"
            title = title.replace("today", "").strip()
        elif "next week" in task_text.lower():
            due_date = (datetime.now() + timedelta(days=7)).isoformat() + "Z"
            title = title.replace("next week", "").strip()

        # Create the task
        try:
            task = await self.api.create_task(
                message.conversation_id,
                TaskCreate(
                    title=title.strip(),
                    priority=priority,
                    due_date=due_date,
                    # Optionally assign to the message sender
                    # assignee_id=message.sender_id
                )
            )

            # Send confirmation with task details
            priority_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}[priority]
            due_text = f"\\n📅 Due: {due_date[:10]}" if due_date else ""

            await self.send_message(
                message.conversation_id,
                MessageLayers(
                    summary=f"✅ Task #{task.id} created\\n\\n"
                           f"{priority_emoji} **{task.title}**{due_text}\\n\\n"
                           f"Status: `{task.status}`",
                    data={"task_id": task.id, "action": "created"}
                )
            )
        except Exception as e:
            await self.send_message(
                message.conversation_id,
                MessageLayers(
                    summary=f"❌ Failed to create task: {e}"
                )
            )

    async def _list_tasks(self, message):
        """List all tasks in the conversation."""
        try:
            tasks = await self.api.list_tasks(message.conversation_id)

            if not tasks:
                await self.send_message(
                    message.conversation_id,
                    MessageLayers(summary="📋 No tasks in this conversation")
                )
                return

            # Group tasks by status
            pending = [t for t in tasks if t.status == "pending"]
            in_progress = [t for t in tasks if t.status == "in_progress"]
            done = [t for t in tasks if t.status == "done"]
            cancelled = [t for t in tasks if t.status == "cancelled"]

            # Build task list message
            lines = ["📋 **Tasks**\\n"]

            if in_progress:
                lines.append("\\n🔄 **In Progress**")
                for task in in_progress:
                    lines.append(f"• #{task.id} {task.title}")

            if pending:
                lines.append("\\n📌 **Pending**")
                for task in pending:
                    emoji = "🔴" if task.priority == "high" else "🟡" if task.priority == "medium" else "🟢"
                    blocked = " 🚫" if task.is_blocked else ""
                    lines.append(f"• #{task.id} {emoji} {task.title}{blocked}")

            if done:
                lines.append("\\n✅ **Completed**")
                for task in done[:5]:  # Show last 5
                    lines.append(f"• #{task.id} ~~{task.title}~~")
                if len(done) > 5:
                    lines.append(f"  ...and {len(done) - 5} more")

            await self.send_message(
                message.conversation_id,
                MessageLayers(
                    summary="\\n".join(lines),
                    data={"task_count": len(tasks)}
                )
            )
        except Exception as e:
            await self.send_message(
                message.conversation_id,
                MessageLayers(summary=f"❌ Failed to list tasks: {e}")
            )

    async def _start_task(self, message, task_id_str: str):
        """Mark a task as in progress."""
        try:
            task_id = int(task_id_str)
            task = await self.api.start_task(task_id)

            await self.send_message(
                message.conversation_id,
                MessageLayers(
                    summary=f"▶️ Started task #{task.id}: **{task.title}**\\n"
                           f"Status: `pending` → `in_progress`",
                    data={"task_id": task.id, "action": "started"}
                )
            )
        except ValueError:
            await self.send_message(
                message.conversation_id,
                MessageLayers(summary="❌ Invalid task ID")
            )
        except Exception as e:
            await self.send_message(
                message.conversation_id,
                MessageLayers(summary=f"❌ Failed to start task: {e}")
            )

    async def _complete_task(self, message, task_id_str: str):
        """Mark a task as complete."""
        try:
            task_id = int(task_id_str)
            task = await self.api.complete_task(task_id)

            await self.send_message(
                message.conversation_id,
                MessageLayers(
                    summary=f"✅ Completed task #{task.id}: **{task.title}**\\n"
                           f"Status: `{task.status}` → `done`",
                    data={"task_id": task.id, "action": "completed"}
                )
            )

            # Check for dependent tasks
            all_tasks = await self.api.list_tasks(message.conversation_id)
            unblocked = [t for t in all_tasks if t.parent_task_id == task_id and t.status == "pending"]

            if unblocked:
                names = ", ".join(f"#{t.id} {t.title}" for t in unblocked)
                await self.send_message(
                    message.conversation_id,
                    MessageLayers(
                        summary=f"🔓 Unblocked tasks: {names}"
                    )
                )
        except ValueError:
            await self.send_message(
                message.conversation_id,
                MessageLayers(summary="❌ Invalid task ID")
            )
        except Exception as e:
            await self.send_message(
                message.conversation_id,
                MessageLayers(summary=f"❌ Failed to complete task: {e}")
            )


async def main():
    """Run the task manager bot."""
    # Get configuration from environment
    base_url = os.getenv("AGENT_IM_BASE_URL", "http://localhost:9800")
    bot_key = os.getenv("AGENT_IM_BOT_KEY")

    if not bot_key:
        print("Error: AGENT_IM_BOT_KEY environment variable required")
        print("Example: export AGENT_IM_BOT_KEY='aim_xxx' or 'aimb_xxx'")
        return

    # Create and run bot
    bot = TaskManagerBot(base_url, bot_key)
    print(f"Task Manager Bot starting...")
    print(f"Connected to: {base_url}")
    print(f"Commands: /task, /tasks, /start, /done")

    try:
        await bot.run()
    except KeyboardInterrupt:
        print("\\nBot stopped by user")
    except Exception as e:
        print(f"Bot error: {e}")


if __name__ == "__main__":
    asyncio.run(main())