"""
variants.py
-----------
Parses UndoVariant objects from the <!--variant YAML --> comment blocks embedded
in benchmark/design_patterns/undo_pattern/*.md, and exposes a module-level
VARIANT_REGISTRY dict.

The Markdown format expected per variant section:

    ### B-1 · Telescoping Constructors ★★★
    **Realism:** ★★★ | ...
    **Smell:** Long Parameter List

    <!--variant
    id: B-1
    realism: 3
    smell: "Long Parameter List"
    task: |
      First line of the task description.
      Second line...
    -->

The comment block is invisible in rendered Markdown but trivially parseable here.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

import yaml

from .models import UndoVariant

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stem → canonical pattern name mapping
# ---------------------------------------------------------------------------

STEM_TO_PATTERN: dict[str, str] = {
    "builder":        "Builder",
    "factory_method": "FactoryMethod",
    "observer":       "Observer",
    "adapter":        "Adapter",
    "composite":      "Composite",
    "decorator":      "Decorator",
    "strategy":       "Strategy",
    "iterator":       "Iterator",
    "visitor":        "Visitor",
    "command":        "Command",
}


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class MarkdownVariantParser:
    """
    Parses ``<!--variant ... -->`` YAML blocks from undo_pattern/*.md files
    and returns ``UndoVariant`` objects sorted by realism (descending).
    """

    # Matches the variant heading + everything up to (and including) the
    # <!--variant ... --> HTML comment block.
    _BLOCK_RE = re.compile(
        r"###\s+(?P<heading>[^\n]+)\n"   # heading line
        r"(?:(?!###).)*?"               # any prose before the comment (non-greedy)
        r"<!--variant\n(?P<yaml>.+?)-->",  # YAML comment block
        re.DOTALL,
    )

    # Extract the human-readable name from the heading, dropping ID prefix and stars.
    # e.g. "B-1 · Telescoping Constructors ★★★" → "Telescoping Constructors"
    _NAME_RE = re.compile(
        r"^[A-Z][a-z\d-]*-\d+\s*[·•]\s*(?P<name>.+?)\s*[★☆]+\s*$"
    )

    def _extract_name(self, heading: str) -> str:
        m = self._NAME_RE.match(heading.strip())
        if m:
            return m.group("name").strip()
        # Fallback: strip leading ID-like token
        parts = heading.split("·", 1)
        if len(parts) == 2:
            return re.sub(r"[★☆]+$", "", parts[1]).strip()
        return heading.strip()

    def parse_file(self, path: Path) -> list[UndoVariant]:
        """Parse all variant blocks from a single Markdown file."""
        text = path.read_text(encoding="utf-8")
        variants: list[UndoVariant] = []

        for m in self._BLOCK_RE.finditer(text):
            heading = m.group("heading")
            yaml_src = m.group("yaml")

            try:
                data = yaml.safe_load(yaml_src)
            except yaml.YAMLError as e:
                logger.warning("YAML parse error in %s (heading=%r): %s", path.name, heading, e)
                continue

            if not isinstance(data, dict):
                logger.warning("Expected dict in variant block, got %s in %s", type(data), path.name)
                continue

            try:
                variants.append(
                    UndoVariant(
                        id=str(data["id"]),
                        name=self._extract_name(heading),
                        realism=int(data["realism"]),
                        smell=str(data["smell"]),
                        task_template=str(data["task"]).strip(),
                    )
                )
            except (KeyError, ValueError) as e:
                logger.warning("Incomplete variant block in %s (heading=%r): %s", path.name, heading, e)

        return sorted(variants, key=lambda v: -v.realism)

    def build_registry(self, md_dir: Path) -> dict[str, list[UndoVariant]]:
        """
        Build a registry mapping pattern name → list[UndoVariant] (by realism desc)
        from all *.md files in *md_dir* whose stem is in STEM_TO_PATTERN.
        """
        registry: dict[str, list[UndoVariant]] = {}

        for md_file in sorted(md_dir.glob("*.md")):
            stem = md_file.stem
            pattern_name = STEM_TO_PATTERN.get(stem)
            if pattern_name is None:
                continue

            parsed = self.parse_file(md_file)
            if parsed:
                registry[pattern_name] = parsed
                logger.debug(
                    "Loaded %d variant(s) for %s from %s", len(parsed), pattern_name, md_file.name
                )
            else:
                logger.warning("No variant blocks found in %s", md_file.name)

        return registry


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

# Canonical location of the Markdown files relative to this source file:
#   refagent/benchmark/design_patterns/undo_pattern/variants.py
#   → parents[4] = project root
#   → / "benchmark/design_patterns/undo_pattern"
_DEFAULT_MD_DIR = (
    Path(__file__).parents[4] / "benchmark" / "design_patterns" / "undo_pattern"
)

def load_registry(md_dir: Optional[Path] = None) -> dict[str, list[UndoVariant]]:
    """Load (or reload) the variant registry from the given directory."""
    target = md_dir or _DEFAULT_MD_DIR
    if not target.exists():
        logger.error("Markdown directory not found: %s", target)
        return {}
    return MarkdownVariantParser().build_registry(target)


# Eager load at import time so callers can use VARIANT_REGISTRY directly.
VARIANT_REGISTRY: dict[str, list[UndoVariant]] = load_registry()
