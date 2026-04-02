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

import hashlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Optional, Any

import git

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from refagent.benchmark.design_patterns.models import GoFPattern
from refagent.benchmark.design_patterns.pattern_first.models import (
    DetectionSource,
    PatternInstance,
)

logger = logging.getLogger(__name__)


def _get_content_hash(content: str) -> str:
    """Return a SHA-256 hash of the string content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


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


# ---------------------------------------------------------------------------
# 1A Detector
# ---------------------------------------------------------------------------

class NameHeuristicDetector:
    """
    Phase 1A: walks every .java file in a local repo (at HEAD) and yields
    PatternInstance objects for files whose class name matches a pattern keyword.

    Parameters
    ----------
    skip_tests : bool
        If True, skip files inside common test directories.
    """

    def __init__(self, skip_tests: bool = True) -> None:
        self.skip_tests = skip_tests

    def detect(
        self,
        repo_path: Path,
        max_new_patterns: int = -1,
        cache: Optional[dict[str, Any]] = None,
        model_name: str = "gpt-5-mini",
    ) -> list[PatternInstance]:
        """
        Scan repository for pattern candidates.
        
        If max_new_patterns > 0 and cache is provided, the detector will stop
        after finding N 'new' patterns (those not already in the cache).
        Previously cached 'YES' results are also returned.
        """
        instances: list[PatternInstance] = []
        new_count = 0
        
        # We scan as many files as needed
        for java_file in repo_path.rglob("*.java"):
            rel = java_file.relative_to(repo_path)
            if self.skip_tests and _is_skippable(rel):
                continue

            class_name = _class_name_from_path(java_file)
            matched_patterns = _match_class_name(class_name)
            if not matched_patterns:
                continue

            # For matches, we check the cache to see if they are 'new'
            try:
                content = java_file.read_text(encoding="utf-8", errors="replace")
                content_hash = _get_content_hash(content)
            except Exception as exc:
                logger.debug("Could not read %s: %s", java_file, exc)
                continue

            for pattern in matched_patterns:
                cache_key = f"{model_name}:{pattern}:{content_hash}"
                
                if cache is not None and cache_key in cache:
                    cached = cache[cache_key]
                    if cached.get("is_valid"):
                        # Already known to be a match
                        instances.append(PatternInstance(
                            file_path=str(rel),
                            class_name=class_name,
                            pattern=pattern,
                            detection_source=DetectionSource.LLM_VALIDATION,
                            confidence=cached.get("confidence", 0.8),
                            reasoning=cached.get("reasoning", "Cached result"),
                        ))
                    continue

                # It's a NEW pattern instance
                instances.append(PatternInstance(
                    file_path=str(rel),
                    class_name=class_name,
                    pattern=pattern,
                    detection_source=DetectionSource.NAME_HEURISTIC,
                    confidence=0.6,
                ))
                new_count += 1
                
            # Early exit if we reached the limit of NEW patterns
            if 0 < max_new_patterns <= new_count:
                logger.info(
                    "[NameHeuristic] Reached max_new_patterns limit (%d). Found %d total instances.",
                    max_new_patterns, len(instances)
                )
                break

        logger.info("[NameHeuristic] %s: %d total instances (including cached valid ones)", repo_path.name, len(instances))
        return instances


# ---------------------------------------------------------------------------
# 1B Detector (adds LLM confirmation on top of 1A results)
# ---------------------------------------------------------------------------

class LLMPatternDetector:
    """
    Phase 1B: Uses an LLM to validate whether a file actually implements
    the suspected design pattern.
    """

    def __init__(self, model_name: str = "gpt-5-mini") -> None:
        self.model_name = model_name
        self.model = ChatOpenAI(model=model_name, temperature=1)

    def refine(
        self,
        repo_path: Path,
        instances: list[PatternInstance],
        cache: Optional[dict[str, Any]] = None,
    ) -> list[PatternInstance]:
        """
        Given a list of PatternInstance objects (from NameHeuristicDetector),
        refine them using an LLM.
        """
        refined: list[PatternInstance] = []
        for inst in instances:
            full_path = repo_path / inst.file_path
            if not full_path.exists():
                continue
            try:
                content = full_path.read_text(encoding="utf-8", errors="replace")
            except Exception as exc:
                logger.debug("Could not read %s: %s", full_path, exc)
                continue

            # Cache lookup
            content_hash = _get_content_hash(content)
            # Cache key incorporates model, pattern and content hash
            cache_key = f"{self.model_name}:{inst.pattern}:{content_hash}"
            
            if cache is not None and cache_key in cache:
                cached = cache[cache_key]
                if cached.get("is_valid"):
                    logger.debug("[LLM Cache] Hit for %s (%s)", inst.file_path, inst.pattern)
                    refined.append(inst.model_copy(update={
                        "detection_source": DetectionSource.LLM_VALIDATION,
                        "confidence": cached.get("confidence", 0.8),
                        "reasoning": cached.get("reasoning", "Cached result"),
                    }))
                else:
                    logger.debug("[LLM Cache] Negative hit for %s (%s)", inst.file_path, inst.pattern)
                continue

            # LLM Prompt
            system_prompt = (
                "You are an expert software architect specialized in design patterns. "
                "Your task is to analyze the provided Java source code and determine if it "
                "implements the specified GoF design pattern. "
                "Respond in the following format:\n"
                "Verdict: [YES/NO]\n"
                "Confidence: [0.0 to 1.0]\n"
                "Reasoning: [Short explanation]"
            )
            human_msg = (
                f"File: {inst.file_path}\n"
                f"Class Name: {inst.class_name}\n"
                f"Suspected Pattern: {inst.pattern}\n"
                f"Initial Confidence (Name Heuristic): {inst.confidence}\n\n"
                f"Source Code:\n```java\n{content}\n```"
            )

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_msg),
            ]

            try:
                response = self.model.invoke(messages)
                res_text = response.content

                is_valid = "VERDICT: YES" in res_text.upper()

                # Extract reasoning
                reasoning = "N/A"
                if "Reasoning:" in res_text:
                    reasoning = res_text.split("Reasoning:")[1].strip()

                # Extract confidence
                conf = 0.8  # default if parsing fails
                if "Confidence:" in res_text:
                    try:
                        # Extract the first number after 'Confidence:'
                        conf_match = re.search(r'Confidence:\s*([0-9.]+)', res_text)
                        if conf_match:
                            conf = float(conf_match.group(1))
                    except:
                        pass

                # Update cache
                if cache is not None:
                    cache[cache_key] = {
                        "is_valid": is_valid,
                        "confidence": conf,
                        "reasoning": reasoning,
                    }

                if is_valid:
                    refined.append(inst.model_copy(update={
                        "detection_source": DetectionSource.LLM_VALIDATION,
                        "confidence": conf,
                        "reasoning": reasoning,
                    }))
                else:
                    logger.debug("[LLM] Pattern %s rejected for %s: %s", inst.pattern, inst.file_path, reasoning)

            except Exception as e:
                logger.error("LLM call failed for %s: %s", inst.file_path, e)
                # If LLM fails, we fall back to the Name Heuristic instance
                refined.append(inst)

        # Deduplicate: same (file_path, pattern) pair, keep highest confidence
        best: dict[tuple[str, str], PatternInstance] = {}
        for inst in refined:
            key = (inst.file_path, str(inst.pattern))
            if key not in best or inst.confidence > best[key].confidence:
                best[key] = inst

        result = list(best.values())
        logger.info("[LLM] Refined to %d instances for %s", len(result), repo_path.name)
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
# Convenience: run 1A (+ 1B) together
# ---------------------------------------------------------------------------

def detect_patterns(
    repo_path: Path,
    llm_model: Optional[str] = None,
    max_new_patterns: int = 10,
    cache: Optional[dict[str, Any]] = None,
) -> list[PatternInstance]:
    """
    Run Phase 1A (name heuristic) followed by Phase 1B (LLM refinement if model provided)
    and return the merged, deduplicated list of PatternInstance objects.
    
    This function stops scanning the repository once ``max_new_patterns`` new
    candidates are found (those not already in the cache).
    """
    name_detector = NameHeuristicDetector()
    all_heuristic = name_detector.detect(
        repo_path,
        max_new_patterns=max_new_patterns if llm_model else -1,
        cache=cache,
        model_name=llm_model or "gpt-5-mini",
    )

    # Split into those already validated (cached) and those that are 'new'
    cached_valid = [
        inst for inst in all_heuristic 
        if inst.detection_source == DetectionSource.LLM_VALIDATION
    ]
    new_to_validate = [
        inst for inst in all_heuristic 
        if inst.detection_source == DetectionSource.NAME_HEURISTIC
    ]

    if llm_model and new_to_validate:
        llm_detector = LLMPatternDetector(model_name=llm_model)
        refined_new = llm_detector.refine(repo_path, new_to_validate, cache=cache)
        return cached_valid + refined_new

    return all_heuristic
