"""
models.py
---------
Pydantic data models for the undo-pattern pipeline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field


class UndoVariant(BaseModel):
    """A single way to 'undo' (inverse-transform) a design pattern."""

    id: str = Field(..., description="Short ID, e.g. 'B-1'")
    name: str = Field(..., description="Human-readable name, from the Markdown heading")
    realism: int = Field(..., ge=1, le=3, description="Realism rating: 3=high, 2=medium, 1=low")
    smell: str = Field(..., description="Primary code smell introduced")
    task_template: str = Field(
        ...,
        description=(
            "Multi-line task description template. "
            "Placeholders: {class_name}, {pattern_file}, {pattern}, {smell}, "
            "{build_cmd}, {test_cmd}, {variant_id}, {variant_name}"
        ),
    )


class UndoTask(BaseModel):
    """One (candidate × variant) unit of work dispatched to OpenHands."""

    task_id: str = Field(..., description="'{candidate_id}__{variant_id}'")
    candidate_id: str
    pattern: str
    repo_path: str = Field(..., description="Absolute local path to the project repo")
    pattern_file: str = Field(..., description="Repo-relative path to the pattern class file")
    class_name: str

    variant: UndoVariant
    task_prompt: str = Field(..., description="Fully rendered task sent to OpenHands")

    docker_image: Optional[str] = Field(None, description="Docker image tag for sandbox")
    docker_mount_path: Optional[str] = Field(
        None, description="Path inside container where repo is mounted"
    )
    build_cmd: Optional[str] = Field(None, description="Command to build (compile) the project")
    test_cmd: Optional[str] = Field(None, description="Command to run the test suite")

    status: Literal["pending", "running", "done", "failed"] = "pending"
    openhands_exit_code: Optional[int] = None
    git_commit_sha: Optional[str] = Field(
        None, description="SHA of the commit made by the OpenHands agent"
    )
    patch_path: Optional[str] = Field(
        None, description="Absolute path to the .patch file capturing agent changes"
    )
    error: Optional[str] = None

    def render_prompt(self) -> str:
        """Return a fully rendered task prompt (placeholders already substituted)."""
        return self.task_prompt
