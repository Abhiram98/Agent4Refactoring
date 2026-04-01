"""
pattern_detector.py  –  Phase 1
---------------------------------
Detect GoF pattern instances in the current HEAD of a local git repository.

Two detection strategies are implemented:

  1A  NameHeuristicDetector   – walks .java files; matches filenames / class
                                names against per-pattern keyword lists.
  1B  StructuralDetector      – reads each candidate file's content and checks
                                for structural signatures using regex (no AST
                                dependency).

Additionally, DpdfDatasetDetector seeds directly from dpdf_dataset.json for
repos whose pattern instances are already catalogued.

All detectors implement the same interface:
    def detect(repo_path: Path) -> list[PatternInstance]
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Optional

import git

from refagent.benchmark.design_patterns.models import GoFPattern
from refagent.benchmark.design_patterns.pattern_first.models import (
    DetectionSource,
    PatternInstance,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1A – Per-pattern keyword lists (matched against the Java simple class name)
# ---------------------------------------------------------------------------

# Maps GoFPattern → list of case-insensitive substrings that strongly suggest
# the file realises that pattern.
PATTERN_CLASS_KEYWORDS: dict[str, list[str]] = {
    GoFPattern.BUILDER:          ["builder"],
    GoFPattern.ABSTRACT_FACTORY: ["abstractfactory"],
    GoFPattern.FACTORY_METHOD:   ["factory"],
    GoFPattern.STRATEGY:         ["strategy"],
    GoFPattern.OBSERVER:         ["observer", "listener", "watcher", "subscriber"],
    GoFPattern.DECORATOR:        ["decorator", "wrapper"],
    GoFPattern.PROXY:            ["proxy"],
    GoFPattern.SINGLETON:        ["singleton"],
    GoFPattern.FACADE:           ["facade"],
    GoFPattern.ADAPTER:          ["adapter"],
    GoFPattern.VISITOR:          ["visitor"],
    GoFPattern.COMMAND:          ["command", "handler", "action"],
    GoFPattern.TEMPLATE_METHOD:  ["template"],
    GoFPattern.COMPOSITE:        ["composite"],
    GoFPattern.STATE:            ["state"],
    GoFPattern.PROTOTYPE:        ["prototype"],
    GoFPattern.CHAIN_OF_RESP:    ["chain", "chainofresponsibility"],
    GoFPattern.MEMENTO:          ["memento"],
    GoFPattern.MEDIATOR:         ["mediator"],
    GoFPattern.ITERATOR:         ["iterator"],
    GoFPattern.FLYWEIGHT:        ["flyweight"],
}

# Implements-clause keywords (lower-cased)
PATTERN_INTERFACE_KEYWORDS: dict[str, list[str]] = {
    GoFPattern.STRATEGY:        ["strategy"],
    GoFPattern.OBSERVER:        ["observer", "listener", "eventhandler"],
    GoFPattern.COMMAND:         ["command", "action", "runnable"],
    GoFPattern.VISITOR:         ["visitor"],
    GoFPattern.FACTORY_METHOD:  ["factory"],
    GoFPattern.ABSTRACT_FACTORY:["abstractfactory", "factory"],
    GoFPattern.ITERATOR:        ["iterator"],
    GoFPattern.DECORATOR:       ["decorator"],
    GoFPattern.PROXY:           ["proxy"],
    GoFPattern.STATE:           ["state"],
    GoFPattern.MEDIATOR:        ["mediator"],
}

# Directories to skip entirely
_SKIP_DIRS = {
    "test", "tests", "it", "target", "build", ".git", "__pycache__",
    "generated-sources", "generated", "node_modules", ".gradle",
}


def _is_skippable(path: Path) -> bool:
    return any(part.lower() in _SKIP_DIRS for part in path.parts)


def _class_name_from_path(java_path: Path) -> str:
    """Extract the simple class name from a .java file path (strips .java)."""
    return java_path.stem


def _match_class_name(class_name: str) -> list[GoFPattern]:
    """Return GoF patterns whose keywords appear in the class name (case-insensitive)."""
    lower = class_name.lower()
    matched: list[GoFPattern] = []
    for pattern, keywords in PATTERN_CLASS_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            matched.append(GoFPattern(pattern))
    return matched


def _match_implements(content: str) -> list[GoFPattern]:
    """Check the implements clause of a Java file for pattern-related interface names."""
    impl_match = re.search(r'\bimplements\s+([\w\s,<>]+)', content)
    if not impl_match:
        return []
    clause = impl_match.group(1).lower()
    matched: list[GoFPattern] = []
    for pattern, keywords in PATTERN_INTERFACE_KEYWORDS.items():
        if any(kw in clause for kw in keywords):
            matched.append(GoFPattern(pattern))
    return matched


# ---------------------------------------------------------------------------
# 1B – Structural heuristics (regex on file content)
# ---------------------------------------------------------------------------

def _structural_check(pattern: GoFPattern, content: str) -> bool:
    """
    Return True if the file content has the structural signature expected for
    ``pattern``.  These are intentionally simple regex checks — a high false-
    positive rate is acceptable here; the greenfield filter handles precision.
    """
    p = pattern.value if hasattr(pattern, 'value') else pattern

    if p == GoFPattern.BUILDER or p == "Builder":
        has_build  = bool(re.search(r'\bpublic\s+\w[\w<>, ]*\s+build\s*\(\s*\)', content))
        has_fluent = bool(re.search(r'\breturn\s+this\b', content))
        return has_build and has_fluent

    if p in (GoFPattern.SINGLETON, "Singleton"):
        has_static  = bool(re.search(r'\bprivate\s+static\b', content))
        has_get_ins = bool(re.search(r'\bgetInstance\s*\(', content))
        return has_static and has_get_ins

    if p in (GoFPattern.DECORATOR, "Decorator", GoFPattern.PROXY, "Proxy"):
        # Implements an interface AND has a field of that same interface type
        impl_m = re.search(r'\bimplements\s+([\w<>]+)', content)
        if not impl_m:
            return False
        iface = impl_m.group(1).split('<')[0]
        has_field = bool(re.search(rf'\bprivate\s+(?:final\s+)?{re.escape(iface)}\b', content))
        return has_field

    if p in (GoFPattern.OBSERVER, "Observer"):
        has_list   = bool(re.search(r'\bList<.*(?:Listener|Observer|Handler|Subscriber)\b', content))
        has_notify = bool(re.search(r'\b(?:notify|fire(?:Event)?|dispatch)\w*\s*\(', content))
        return has_list or has_notify

    if p in (GoFPattern.STRATEGY, "Strategy"):
        is_iface    = bool(re.search(r'\binterface\b', content))
        has_action  = bool(re.search(r'\b(?:execute|apply|process|handle|perform|compute)\s*\(', content))
        return is_iface and has_action

    if p in (GoFPattern.FACTORY_METHOD, "FactoryMethod", GoFPattern.ABSTRACT_FACTORY, "AbstractFactory"):
        has_create  = bool(re.search(r'\bcreate\w*\s*\(', content))
        has_ret_new = bool(re.search(r'\breturn\s+new\s+\w', content))
        return has_create or has_ret_new

    if p in (GoFPattern.COMMAND, "Command"):
        has_execute = bool(re.search(r'\bvoid\s+execute\s*\(\s*\)', content))
        return has_execute

    if p in (GoFPattern.TEMPLATE_METHOD, "TemplateMethod"):
        has_final    = bool(re.search(r'\bfinal\b', content))
        has_abstract = bool(re.search(r'\babstract\b', content))
        return has_final and has_abstract

    if p in (GoFPattern.VISITOR, "Visitor"):
        has_visit = bool(re.search(r'\bvisit\s*\(', content))
        return has_visit

    if p in (GoFPattern.COMPOSITE, "Composite"):
        has_list_of_self = bool(re.search(r'\bList<\w*(?:Component|Composite|Node|Element)\b', content))
        return has_list_of_self

    # For other patterns, rely on name heuristic alone (structural check passes)
    return True


# ---------------------------------------------------------------------------
# 1A Detector
# ---------------------------------------------------------------------------

class NameHeuristicDetector:
    """
    Phase 1A: walks every .java file in a local repo (at HEAD) and yields
    PatternInstance objects for files whose class name matches a pattern keyword.

    Parameters
    ----------
    max_files : int
        Hard cap to avoid very large repos taking too long.
    skip_tests : bool
        If True, skip files inside common test directories.
    """

    def __init__(self, max_files: int = 10_000, skip_tests: bool = True) -> None:
        self.max_files  = max_files
        self.skip_tests = skip_tests

    def detect(self, repo_path: Path) -> list[PatternInstance]:
        instances: list[PatternInstance] = []
        count = 0
        for java_file in repo_path.rglob("*.java"):
            if count >= self.max_files:
                logger.warning("Reached max_files limit (%d) in %s", self.max_files, repo_path)
                break
            rel = java_file.relative_to(repo_path)
            if self.skip_tests and _is_skippable(rel):
                continue
            count += 1

            class_name = _class_name_from_path(java_file)
            matched_patterns = _match_class_name(class_name)
            if not matched_patterns:
                continue

            for pattern in matched_patterns:
                instances.append(PatternInstance(
                    file_path=str(rel),
                    class_name=class_name,
                    pattern=pattern,
                    detection_source=DetectionSource.NAME_HEURISTIC,
                    confidence=0.6,
                ))

        logger.info("[NameHeuristic] %s: %d candidate instances found", repo_path.name, len(instances))
        return instances


# ---------------------------------------------------------------------------
# 1B Detector (adds structural confirmation on top of 1A results)
# ---------------------------------------------------------------------------

class StructuralDetector:
    """
    Phase 1B: reads each candidate file's content and runs a fast regex-based
    structural check.  Instances that fail structural validation are either
    downgraded (lower confidence) or removed depending on ``strict`` mode.

    Parameters
    ----------
    strict : bool
        If True, drop instances that fail their structural check.
        If False, keep them but mark confidence as 0.4 (name only).
    """

    def __init__(self, strict: bool = False) -> None:
        self.strict = strict

    def refine(self, repo_path: Path, instances: list[PatternInstance]) -> list[PatternInstance]:
        """
        Given a list of PatternInstance objects (from NameHeuristicDetector),
        refine them using structural checks.
        """
        refined: list[PatternInstance] = []
        for inst in instances:
            full_path = repo_path / inst.file_path
            if not full_path.exists():
                if not self.strict:
                    refined.append(inst)
                continue
            try:
                content = full_path.read_text(encoding="utf-8", errors="replace")
            except Exception as exc:
                logger.debug("Could not read %s: %s", full_path, exc)
                if not self.strict:
                    refined.append(inst)
                continue

            # Also check implements clause for a second pattern signal
            impl_patterns = _match_implements(content)
            if impl_patterns and inst.pattern not in impl_patterns:
                # The implements clause suggests a different (or additional) pattern
                for extra in impl_patterns:
                    if extra != inst.pattern:
                        refined.append(inst.model_copy(update={
                            "pattern": extra,
                            "detection_source": DetectionSource.STRUCTURAL,
                            "confidence": 0.65,
                        }))

            passes = _structural_check(inst.pattern, content)
            if passes:
                refined.append(inst.model_copy(update={
                    "detection_source": DetectionSource.STRUCTURAL,
                    "confidence": 0.85,
                }))
            elif not self.strict:
                # Keep with lower confidence, name-heuristic only
                refined.append(inst.model_copy(update={"confidence": 0.4}))

        # Deduplicate: same (file_path, pattern) pair, keep highest confidence
        best: dict[tuple[str, str], PatternInstance] = {}
        for inst in refined:
            key = (inst.file_path, str(inst.pattern))
            if key not in best or inst.confidence > best[key].confidence:
                best[key] = inst

        result = list(best.values())
        logger.info("[Structural] Refined to %d instances for %s", len(result), repo_path.name)
        return result


# ---------------------------------------------------------------------------
# dpdf_dataset seed
# ---------------------------------------------------------------------------

def _find_java_file_in_repo(
    repo_path: Path, class_name: str, skip_tests: bool = True
) -> list[str]:
    """
    Search ``repo_path`` for files named ``<class_name>.java`` and return
    their relative paths.  Results are sorted so non-test paths come first.
    """
    target = f"{class_name}.java"
    matches: list[Path] = list(repo_path.rglob(target))

    def _sort_key(p: Path) -> int:
        rel = p.relative_to(repo_path)
        # Prefer src/main over src/test / target / build
        if _is_skippable(rel):
            return 1
        return 0

    matches.sort(key=_sort_key)
    return [str(m.relative_to(repo_path)) for m in matches]


class DpdfDatasetDetector:
    """
    Seeds PatternInstance objects directly from a dpdf_dataset JSON file.

    For each entry the detector tries to resolve a concrete file path in the
    following order:
      1. Use the ``filePath`` field if it is present and not "NOT_FOUND".
      2. Otherwise search the local repo for ``<class_name>.java`` and use
         every match found (sorted: non-test paths first).
      3. If nothing is found the entry is skipped with a warning.

    Parameters
    ----------
    dataset_path : Path
        Path to dpdf_dataset_filtered.json (or the full dpdf_dataset.json).
    project_name : str
        Only load entries for this project (matches the ``project_name`` field).
    skip_tests : bool
        If True, when falling back to file search, prefer non-test paths and
        list test-directory matches last.
    """

    def __init__(self, dataset_path: Path, project_name: str, skip_tests: bool = True) -> None:
        self.dataset_path = dataset_path
        self.project_name = project_name
        self.skip_tests   = skip_tests

    def detect(self, repo_path: Path) -> list[PatternInstance]:
        with open(self.dataset_path) as f:
            dataset = json.load(f)

        instances: list[PatternInstance] = []
        unresolved = 0

        for entry in dataset:
            if entry.get("project_name") != self.project_name:
                continue
            # Only use confirmed pattern instances when the flag is present
            if "is_true_pattern" in entry and not entry["is_true_pattern"]:
                continue

            pattern_str = entry.get("pattern", "")
            try:
                pattern = GoFPattern(pattern_str)
            except ValueError:
                logger.debug("Unknown pattern '%s' in dpdf_dataset; skipping", pattern_str)
                continue

            class_name = entry.get("class_name", "")
            if not class_name:
                logger.debug("Entry missing class_name; skipping %s", entry)
                continue

            # ── Resolve file path ────────────────────────────────────
            raw_path = entry.get("filePath", "")
            resolved_paths: list[str] = []

            if raw_path and raw_path != "NOT_FOUND":
                # Dataset provides a path – verify it actually exists
                candidate = repo_path / raw_path
                if candidate.exists():
                    resolved_paths = [raw_path]
                else:
                    logger.debug(
                        "[DpdfSeed] Provided path does not exist in repo: %s — falling back to search",
                        raw_path,
                    )

            if not resolved_paths:
                # Fallback: search repo filesystem for ClassName.java
                resolved_paths = _find_java_file_in_repo(repo_path, class_name, self.skip_tests)
                if resolved_paths:
                    logger.debug(
                        "[DpdfSeed] Found %s via filesystem search: %s",
                        class_name,
                        resolved_paths,
                    )
                else:
                    logger.warning(
                        "[DpdfSeed] '%s.java' not found anywhere in %s — skipping",
                        class_name, repo_path.name,
                    )
                    unresolved += 1
                    continue

            # Emit one PatternInstance per resolved path
            for file_path in resolved_paths:
                instances.append(PatternInstance(
                    file_path=file_path,
                    class_name=class_name,
                    pattern=pattern,
                    detection_source=DetectionSource.DPDF_SEED,
                    confidence=1.0,
                ))

        logger.info(
            "[DpdfSeed] project='%s' → %d instances resolved, %d unresolvable",
            self.project_name, len(instances), unresolved,
        )
        return instances



# ---------------------------------------------------------------------------
# Convenience: run 1A + 1B together
# ---------------------------------------------------------------------------

def detect_patterns(
    repo_path: Path,
    structural_strict: bool = False,
    max_files: int = 10_000,
) -> list[PatternInstance]:
    """
    Run Phase 1A (name heuristic) followed by Phase 1B (structural refinement)
    and return the merged, deduplicated list of PatternInstance objects.
    """
    name_detector        = NameHeuristicDetector(max_files=max_files)
    structural_detector  = StructuralDetector(strict=structural_strict)

    raw       = name_detector.detect(repo_path)
    refined   = structural_detector.refine(repo_path, raw)
    return refined
