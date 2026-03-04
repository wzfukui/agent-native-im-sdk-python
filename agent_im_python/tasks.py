"""Task management support for Agent-Native IM."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional
from datetime import datetime


@dataclass
class Task:
    """Represents a task in a conversation."""

    id: int
    conversation_id: int
    title: str
    description: str = ""
    priority: str = "medium"  # low/medium/high
    status: str = "pending"   # pending/in_progress/done/cancelled
    assignee_id: Optional[int] = None
    assignee: Optional[dict] = None  # Entity object
    parent_task_id: Optional[int] = None
    parent_task: Optional[Task] = None
    due_date: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""

    @property
    def is_blocked(self) -> bool:
        """Check if task is blocked by parent task."""
        if self.parent_task:
            return self.parent_task.status not in ("done", "cancelled")
        return False

    @property
    def is_overdue(self) -> bool:
        """Check if task is overdue."""
        if not self.due_date:
            return False
        try:
            due = datetime.fromisoformat(self.due_date.replace("Z", "+00:00"))
            return due < datetime.now(due.tzinfo)
        except (ValueError, AttributeError):
            return False

    @classmethod
    def from_dict(cls, data: dict) -> Task:
        """Create Task from API response dict."""
        return cls(
            id=data.get("id", 0),
            conversation_id=data.get("conversation_id", 0),
            title=data.get("title", ""),
            description=data.get("description", ""),
            priority=data.get("priority", "medium"),
            status=data.get("status", "pending"),
            assignee_id=data.get("assignee_id"),
            assignee=data.get("assignee"),
            parent_task_id=data.get("parent_task_id"),
            parent_task=cls.from_dict(data["parent_task"]) if data.get("parent_task") else None,
            due_date=data.get("due_date"),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )


@dataclass
class TaskCreate:
    """Parameters for creating a new task."""

    title: str
    description: str = ""
    priority: str = "medium"
    assignee_id: Optional[int] = None
    parent_task_id: Optional[int] = None
    due_date: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to API request payload."""
        data = {"title": self.title, "priority": self.priority}
        if self.description:
            data["description"] = self.description
        if self.assignee_id is not None:
            data["assignee_id"] = self.assignee_id
        if self.parent_task_id is not None:
            data["parent_task_id"] = self.parent_task_id
        if self.due_date:
            data["due_date"] = self.due_date
        return data


@dataclass
class TaskUpdate:
    """Parameters for updating a task."""

    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    assignee_id: Optional[int] = None
    parent_task_id: Optional[int] = None
    due_date: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to API request payload."""
        data = {}
        if self.title is not None:
            data["title"] = self.title
        if self.description is not None:
            data["description"] = self.description
        if self.priority is not None:
            data["priority"] = self.priority
        if self.status is not None:
            data["status"] = self.status
        if self.assignee_id is not None:
            data["assignee_id"] = self.assignee_id
        if self.parent_task_id is not None:
            data["parent_task_id"] = self.parent_task_id
        if self.due_date is not None:
            data["due_date"] = self.due_date
        return data


class TaskMixin:
    """Mixin to add task management methods to APIClient."""

    async def create_task(self, conversation_id: int, task: TaskCreate) -> Task:
        """Create a new task in a conversation."""
        data = await self._request(
            "POST",
            f"/api/v1/conversations/{conversation_id}/tasks",
            json=task.to_dict()
        )
        return Task.from_dict(data)

    async def list_tasks(self, conversation_id: int) -> list[Task]:
        """List all tasks in a conversation."""
        data = await self._request(
            "GET",
            f"/api/v1/conversations/{conversation_id}/tasks"
        )
        return [Task.from_dict(t) for t in data]

    async def get_task(self, task_id: int) -> Task:
        """Get a specific task by ID."""
        data = await self._request("GET", f"/api/v1/tasks/{task_id}")
        return Task.from_dict(data)

    async def update_task(self, task_id: int, update: TaskUpdate) -> Task:
        """Update a task."""
        data = await self._request(
            "PUT",
            f"/api/v1/tasks/{task_id}",
            json=update.to_dict()
        )
        return Task.from_dict(data)

    async def delete_task(self, task_id: int) -> None:
        """Delete a task."""
        await self._request("DELETE", f"/api/v1/tasks/{task_id}")

    async def start_task(self, task_id: int) -> Task:
        """Mark a task as in progress."""
        return await self.update_task(
            task_id,
            TaskUpdate(status="in_progress")
        )

    async def complete_task(self, task_id: int) -> Task:
        """Mark a task as done."""
        return await self.update_task(
            task_id,
            TaskUpdate(status="done")
        )

    async def cancel_task(self, task_id: int) -> Task:
        """Mark a task as cancelled."""
        return await self.update_task(
            task_id,
            TaskUpdate(status="cancelled")
        )