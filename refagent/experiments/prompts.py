"""
Shared prompt construction for corename benchmark experiments.

Both vanilla_LLM.py and codex_runner.py import from here so there is a
single source of truth for the system message, user message, and seed-name
parsing logic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Seed-name parsing  (same regexes as the original vanilla_LLM.py)
# ---------------------------------------------------------------------------

def parse_seed_name(seed_example: dict) -> tuple[str, str]:
    """
    Extract (old_name, new_name) from a seed_example dict.

    Supports: Rename Class, Method, Variable, Attribute, Parameter.
    Falls back to splitting the codeElement string when no regex matches.
    """
    ref_type = seed_example.get("type", "")
    desc = seed_example.get("description", "")
    old_name = new_name = ""

    if ref_type == "Rename Class":
        m = re.search(
            r"Rename Class .*\.([A-Za-z0-9_]+) renamed to .*\.([A-Za-z0-9_]+)",
            desc,
        )
        if m:
            old_name, new_name = m.group(1), m.group(2)

    elif ref_type == "Rename Method":
        m = re.search(
            r"Rename Method .*? ([A-Za-z0-9_]+)\(.*?\)\s*:\s*.*? renamed to .*? ([A-Za-z0-9_]+)\(",
            desc,
        )
        if m:
            old_name, new_name = m.group(1), m.group(2)

    elif ref_type == "Rename Variable":
        m = re.search(
            r"Rename Variable ([A-Za-z0-9_]+) ?: .*? to ([A-Za-z0-9_]+) ?:",
            desc,
        )
        if m:
            old_name, new_name = m.group(1), m.group(2)

    elif ref_type == "Rename Attribute":
        m = re.search(
            r"Rename Attribute ([A-Za-z0-9_]+) ?: .*? to ([A-Za-z0-9_]+) ?: .*? in class",
            desc,
        )
        if m:
            old_name, new_name = m.group(1), m.group(2)

    elif ref_type == "Rename Parameter":
        m = re.search(
            r"Rename Parameter ([A-Za-z0-9_]+) ?: .*? to ([A-Za-z0-9_]+) ?: .*? in method",
            desc,
        )
        if m:
            old_name, new_name = m.group(1), m.group(2)

    # Fallback: pull from leftSide / rightSide codeElement
    if not old_name:
        left = seed_example.get("leftSideLocations", [{}])[0].get("codeElement", "")
        right = seed_example.get("rightSideLocations", [{}])[0].get("codeElement", "")
        old_name = left.split("(")[0].split(" ")[-1].split(".")[-1]
        new_name = right.split("(")[0].split(" ")[-1].split(".")[-1]

    return old_name, new_name


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

SYSTEM_TEMPLATE = """\
You are a code refactoring assistant. Your task is to rename identifiers in the given Java code.
You will be given a seed rename. Use it to infer the broader naming concept being changed and \
rename ALL occurrences that share the same concept consistently.
Finally, output the entire code.\
"""

USER_TEMPLATE = """\
Please rename the variable '{old_name}' to '{new_name}' in the following code. \
Rename all conceptually related identifiers:

{file_content}

Finally, output the entire code with renames applied.\
"""

# Extra note appended to the system message when an agent has access to an
# IntelliJ MCP rename tool and should prefer it over direct edits.
MCP_RENAME_NOTE = """\

IMPORTANT: Use the IntelliJ MCP `rename_refactoring` tool to perform each \
rename operation. This ensures all cross-file usages are updated atomically \
and consistently via IntelliJ's refactoring engine.\
"""


@dataclass
class RenamePrompt:
    """Holds the system and user parts of the rename prompt."""
    system: str
    user: str

    def as_single_string(self) -> str:
        """Collapse into one string suitable for CLI agents (e.g. codex exec)."""
        return f"{self.system}\n\n{self.user}"


def build_rename_prompt(
    item_data: dict,
    file_content: str,
    old_name: str,
    new_name: str,
    include_mcp_note: bool = False,
) -> RenamePrompt:
    """
    Build the rename prompt shared across vanilla_LLM and codex_runner.

    Parameters
    ----------
    item_data:
        Raw benchmark item dict (may contain improved_commit_message /
        change_summary that enrich the system message).
    file_content:
        The full text of the starting file to be refactored.
    old_name / new_name:
        Parsed from the seed_example via parse_seed_name().
    include_mcp_note:
        When True, appends MCP_RENAME_NOTE to the system message.
        Set this to True in the codex runner.
    """
    improved_commit_message = item_data.get("improved_commit_message", "")
    change_summary = item_data.get("change_summary", "")

    system = SYSTEM_TEMPLATE
    if improved_commit_message:
        system += f"\nPlease perform the following action: {improved_commit_message}"
    if change_summary:
        system += f"\n{change_summary}"
    if include_mcp_note:
        system += MCP_RENAME_NOTE

    user = USER_TEMPLATE.format(
        old_name=old_name,
        new_name=new_name,
        file_content=file_content,
    )

    return RenamePrompt(system=system, user=user)
