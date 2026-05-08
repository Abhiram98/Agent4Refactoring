"""
pipeline.py
-----------
UndoPatternPipeline: loads candidates, builds tasks, invokes OpenHands, and
captures the resulting commit as a .patch file.

Docker interaction
------------------
Each project has a pre-built Docker image (see PROJECT_DOCKER_CONFIG) that
contains the right JDK, build tool, and a warm dependency cache. OpenHands is
told to use this image as its sandbox via a per-run .openhands/config.toml
written into the repo directory. The workspace_mount_path_in_sandbox key makes
OpenHands mount the local code at the path the existing run_build.sh /
run_test.sh scripts expect, so no Dockerfile changes are needed.

Commit & patch capture
----------------------
The task prompt instructs the agent to commit its changes with a recognisable
prefix. After OpenHands exits, the pipeline:
 1. Finds the agent's commit by grepping git log for that prefix.
 2. Runs `git format-patch -1 HEAD --stdout` and writes a .patch file.
 3. Stores the patch path and commit SHA in the task manifest.
If the agent only staged but did not commit, a plain `git diff HEAD` is saved
as a .diff file instead.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from pathlib import Path
from typing import Optional

import refagent.utils.project_manager as pm
from .models import UndoTask, UndoVariant
from .variants import VARIANT_REGISTRY, load_registry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Per-project Docker configuration
# ---------------------------------------------------------------------------

PROJECT_DOCKER_CONFIG: dict[str, dict] = {
    "AxonFramework": {
        "image":      "axon-val",
        "mount_path": "/app/AxonFramework",
        "build_cmd":  "/app/run_build.sh",
        "test_cmd":   "/app/run_test.sh",
    },
    "ant": {
        "image":      "ant-val",
        "mount_path": "/app/ant",
        "build_cmd":  "/app/run_build.sh",
        "test_cmd":   "/app/run_test.sh",
    },
    "camunda": {
        "image":      "camunda-val",
        "mount_path": "/app/camunda",
        "build_cmd":  "/app/run_build.sh",
        "test_cmd":   "/app/run_test.sh",
    },
    "cayenne": {
        "image":      "cayenne-val",
        "mount_path": "/app/cayenne",
        "build_cmd":  "/app/run_build.sh",
        "test_cmd":   "/app/run_test.sh",
    },
    "cucumber-jvm": {
        "image":      "cucumber-jvm-val",
        "mount_path": "/app/cucumber-jvm",
        "build_cmd":  "/app/run_build.sh",
        "test_cmd":   "/app/run_test.sh",
    },
    "flink": {
        "image":      "flink-val",
        "mount_path": "/app/flink",
        "build_cmd":  "/app/run_build.sh",
        "test_cmd":   "/app/run_test.sh",
    },
    "gson": {
        "image":      "gson-val",
        "mount_path": "/app/gson",
        "build_cmd":  "/app/run_build.sh",
        "test_cmd":   "/app/run_test.sh",
    },
    "hbase": {
        "image":      "hbase-val",
        "mount_path": "/app/hbase",
        "build_cmd":  "/app/run_build.sh",
        "test_cmd":   "/app/run_test.sh",
    },
    "jackrabbit": {
        "image":      "jackrabbit-val",
        "mount_path": "/app/jackrabbit",
        "build_cmd":  "/app/run_build.sh",
        "test_cmd":   "/app/run_test.sh",
    },
    "kafka": {
        "image":      "kafka-val",
        "mount_path": "/app/kafka",
        "build_cmd":  "/app/run_build.sh",
        "test_cmd":   "/app/run_test.sh",
    },
}

# Commit message prefix the agent is asked to use. Used to locate the commit
# afterward and generate the patch.
_COMMIT_PREFIX = "[undo-pattern]"

# Standard footer appended to every task prompt.
_TASK_FOOTER_TEMPLATE = """
---
**Verification instructions (follow these exactly):**

1. Ensure that the class `{class_name}` no longer exists, so that the pattern `{pattern}` is not exposed.

2. After making all changes, verify the code compiles by running this shell script:
/Users/abhiram/Documents/TBE/RefactoringAgentProject/Agent4Refactoring/data/design_patterns/docker/hbase/verify_patch.sh
This scripts commits your current changes and tests your patch on a docker container. 
   Fix any compilation errors before continuing.

""".strip()


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class UndoPatternPipeline:
    """
    Orchestrates the undo-pattern dataset generation workflow:
      load_candidates → build_tasks → [for each task] run OpenHands → capture patch
    """

    def __init__(
        self,
        candidate_ids: list[str],
        candidates_path: Path,
        output_path: Path,
        patches_dir: Path,
        num_variants: int = 2,
        dry_run: bool = False,
        md_dir: Optional[Path] = None,
    ) -> None:
        self.candidate_ids = candidate_ids
        self.candidates_path = candidates_path
        self.output_path = output_path
        self.patches_dir = patches_dir
        self.num_variants = num_variants
        self.dry_run = dry_run

        # Allow caller to override the Markdown directory (useful for tests)
        if md_dir is not None:
            self.registry = load_registry(md_dir)
        else:
            self.registry = VARIANT_REGISTRY

        self._done_ids: set[str] = self._load_done_task_ids()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self) -> list[UndoTask]:
        candidates = self._load_candidates()
        if not candidates:
            logger.error("No candidates matched the given IDs: %s", self.candidate_ids)
            return []

        tasks = self._build_tasks(candidates)
        logger.info("Built %d task(s) from %d candidate(s)", len(tasks), len(candidates))

        if self.dry_run:
            self._print_dry_run(tasks)
            return tasks

        self.patches_dir.mkdir(parents=True, exist_ok=True)
        for task in tasks:
            if task.task_id in self._done_ids:
                logger.info("Skipping already-done task: %s", task.task_id)
                continue
            self._run_one(task)

        return tasks

    # ------------------------------------------------------------------
    # Candidate loading
    # ------------------------------------------------------------------

    def _load_candidates(self) -> list[dict]:
        with open(self.candidates_path, "r") as f:
            all_candidates: list[dict] = json.load(f)

        matched = [c for c in all_candidates if c["id"] in self.candidate_ids]
        missing = set(self.candidate_ids) - {c["id"] for c in matched}
        if missing:
            logger.warning("IDs not found in candidates file: %s", sorted(missing))
        return matched

    # ------------------------------------------------------------------
    # Task construction
    # ------------------------------------------------------------------

    def _build_tasks(self, candidates: list[dict]) -> list[UndoTask]:
        tasks: list[UndoTask] = []
        for candidate in candidates:
            pattern = candidate.get("pattern", "")
            variants = self.registry.get(pattern, [])
            if not variants:
                logger.warning("No variants registered for pattern '%s' (candidate %s)",
                               pattern, candidate["id"])
                continue

            top_variants = variants[: self.num_variants]
            repo_name = Path(candidate["repo_path"]).name
            docker_cfg = PROJECT_DOCKER_CONFIG.get(repo_name, {})

            for variant in top_variants:
                task_id = f"{candidate['id']}__{variant.id}"
                commit_msg = (
                    f"{_COMMIT_PREFIX} {variant.id}: {variant.name} "
                    f"for {candidate['class_name']}"
                )
                build_cmd = docker_cfg.get("build_cmd", "mvn clean install -DskipTests")

                prompt = self._render_prompt(candidate, variant, docker_cfg, commit_msg)

                tasks.append(
                    UndoTask(
                        task_id=task_id,
                        candidate_id=candidate["id"],
                        pattern=pattern,
                        repo_path=candidate["repo_path"],
                        pattern_file=candidate.get("pattern_file", ""),
                        class_name=candidate.get("class_name", ""),
                        variant=variant,
                        task_prompt=prompt,
                        docker_image=docker_cfg.get("image"),
                        docker_mount_path=docker_cfg.get("mount_path"),
                        build_cmd=docker_cfg.get("build_cmd"),
                        test_cmd=docker_cfg.get("test_cmd"),
                        status="pending",
                    )
                )
        return tasks

    def _render_prompt(
        self,
        candidate: dict,
        variant: UndoVariant,
        docker_cfg: dict,
        commit_msg: str,
    ) -> str:
        build_cmd = docker_cfg.get("build_cmd", "the project's build command")
        test_cmd  = docker_cfg.get("test_cmd",  "the project's test command")

        body = variant.task_template.format(
            class_name=candidate.get("class_name", ""),
            pattern_file=candidate.get("pattern_file", ""),
            pattern=candidate.get("pattern", ""),
            smell=variant.smell,
            build_cmd=build_cmd,
            test_cmd=test_cmd,
            variant_id=variant.id,
            variant_name=variant.name,
        )

        footer = _TASK_FOOTER_TEMPLATE.format(
            class_name=candidate.get("class_name", ""),
            pattern=candidate.get("pattern", ""),
        )

        return f"{body}\n\n{footer}"

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def _run_one(self, task: UndoTask) -> None:
        repo_path = Path(task.repo_path)
        if not repo_path.exists():
            logger.error("Repo path does not exist: %s", repo_path)
            task.status = "failed"
            task.error = f"Repo path not found: {repo_path}"
            self._append_manifest(task)
            return

        docker_cfg = PROJECT_DOCKER_CONFIG.get(repo_path.name, {})
        config_toml_path: Optional[Path] = None

        try:

            # Reset git to head.
            project = pm.EvalProject(repo_path.name)
            project.checkout_branch("master")
            # create a new branch with the task id.
            project.checkout_branch(task.task_id)

            # 1. Ensure .openhands/ is git-excluded (local exclude, not committed)
            self._ensure_openhands_excluded(repo_path)

            # 2. Write per-run config.toml into .openhands/
            if docker_cfg:
                # config_toml_path = self._write_config_toml(repo_path, docker_cfg)
                pass
            else:
                logger.warning(
                    "No Docker config for project '%s'; running without custom sandbox.",
                    repo_path.name,
                )

            # 3. Record as running
            task.status = "running"
            self._append_manifest(task)
            logger.info("▶ Running task %s  [%s / %s]", task.task_id, task.pattern, task.variant.id)

            # 4. Invoke OpenHands
            result = subprocess.run(
                ["openhands", "--headless", "--always-approve", "-t", task.task_prompt],
                cwd=repo_path,
                capture_output=True,
                text=True,
            )
            task.openhands_exit_code = result.returncode
            logger.info(
                "  OpenHands exited with code %d for task %s",
                result.returncode, task.task_id,
            )

            # changed_files = project.get_changed_files()
            # project.safe_add(changed_files)
            # project.commit(f"refactor for {task.task_id}")

            # 5. Capture patch / diff
            commit_sha, patch_path = self._capture_output(repo_path, task.task_id, task.class_name)
            task.git_commit_sha = commit_sha
            task.patch_path = str(patch_path) if patch_path else None

            task.status = "done" if result.returncode == 0 else "failed"
            if result.returncode != 0:
                task.error = result.stderr[-2000:].strip() or result.stdout[-2000:].strip()

        except Exception as exc:
            logger.exception("Unexpected error running task %s", task.task_id)
            task.status = "failed"
            task.error = str(exc)

        finally:
            # 6. Clean up config.toml (always, even on failure)
            if config_toml_path and config_toml_path.exists():
                try:
                    config_toml_path.unlink()
                except OSError:
                    pass

            self._append_manifest(task)
            logger.info(
                "  Task %s → %s  (commit=%s  patch=%s)",
                task.task_id, task.status, task.git_commit_sha, task.patch_path,
            )

    # ------------------------------------------------------------------
    # Git helpers
    # ------------------------------------------------------------------

    def _ensure_openhands_excluded(self, repo_path: Path) -> None:
        """
        Add '.openhands/' to .git/info/exclude (repo-local, not committed)
        so the agent's commit never accidentally includes our config files.
        """
        exclude_file = repo_path / ".git" / "info" / "exclude"
        exclude_file.parent.mkdir(parents=True, exist_ok=True)
        content = exclude_file.read_text() if exclude_file.exists() else ""
        if ".openhands/" not in content:
            with open(exclude_file, "a") as f:
                f.write("\n# Added by undo-pattern pipeline\n.openhands/\n")
            logger.debug("Added .openhands/ to .git/info/exclude for %s", repo_path.name)

    def _capture_output(
        self, repo_path: Path, task_id: str, class_name: str
    ) -> tuple[Optional[str], Optional[Path]]:
        """
        Try to find the agent's commit and save it as a .patch file.
        Falls back to `git diff HEAD` and saves a .diff file.
        Returns (commit_sha, patch_file_path).
        """
        # Search for the most recent commit whose message starts with [undo-pattern]
        log_result = subprocess.run(
            ["git", "log", "--oneline", f"--grep={_COMMIT_PREFIX}", "-1", "--format=%H %s"],
            cwd=repo_path, capture_output=True, text=True,
        )
        commit_line = log_result.stdout.strip()

        if commit_line:
            commit_sha = commit_line.split()[0]
            # Generate patch from that commit
            patch_result = subprocess.run(
                ["git", "format-patch", "-1", commit_sha, "--stdout"],
                cwd=repo_path, capture_output=True, text=True,
            )
            patch_path = self.patches_dir / f"{task_id}.patch"
            patch_path.write_text(patch_result.stdout)
            logger.info("  Captured commit %s as %s", commit_sha[:8], patch_path.name)
            return commit_sha, patch_path

        # No commit found — try staged/unstaged diff
        diff_result = subprocess.run(
            ["git", "diff", "HEAD"],
            cwd=repo_path, capture_output=True, text=True,
        )
        if diff_result.stdout.strip():
            diff_path = self.patches_dir / f"{task_id}.diff"
            diff_path.write_text(diff_result.stdout)
            logger.info("  No commit found; saved uncommitted diff as %s", diff_path.name)
            return None, diff_path

        logger.warning("  No commit and no diff found for task %s", task_id)
        return None, None

    # ------------------------------------------------------------------
    # OpenHands config.toml
    # ------------------------------------------------------------------

    def _write_config_toml(self, repo_path: Path, docker_cfg: dict) -> Path:
        config_dir = repo_path / ".openhands"
        config_dir.mkdir(exist_ok=True)
        toml_path = config_dir / "config.toml"
        toml_path.write_text(
            "[sandbox]\n"
            f'base_container_image = "{docker_cfg["image"]}"\n'
            f'workspace_mount_path_in_sandbox = "{docker_cfg["mount_path"]}"\n'
        )
        return toml_path

    # ------------------------------------------------------------------
    # Manifest I/O
    # ------------------------------------------------------------------

    def _load_done_task_ids(self) -> set[str]:
        """Return the set of task_ids already marked 'done' in the manifest."""
        done: set[str] = set()
        if not self.output_path.exists():
            return done
        with open(self.output_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    if record.get("status") == "done":
                        done.add(record["task_id"])
                except json.JSONDecodeError:
                    pass
        return done

    def _append_manifest(self, task: UndoTask) -> None:
        """Append the task's current state as a JSON line to the manifest."""
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        record = task.model_dump(mode="json")
        # Flatten variant to avoid nested objects for readability
        record["variant_id"]   = task.variant.id
        record["variant_name"] = task.variant.name
        record["variant_realism"] = task.variant.realism
        record["variant_smell"]   = task.variant.smell
        del record["variant"]   # remove nested object; keep flat fields above

        with open(self.output_path, "a") as f:
            f.write(json.dumps(record) + "\n")

    # ------------------------------------------------------------------
    # Dry run
    # ------------------------------------------------------------------

    def _print_dry_run(self, tasks: list[UndoTask]) -> None:
        sep = "─" * 72
        for task in tasks:
            print(sep)
            print(f"Task ID    : {task.task_id}")
            print(f"Candidate  : {task.candidate_id}  ({task.pattern} / {task.class_name})")
            print(f"Variant    : {task.variant.id} – {task.variant.name} [★{'★' * (task.variant.realism - 1)}]")
            print(f"Repo       : {task.repo_path}")
            print(f"File       : {task.pattern_file}")
            print(f"Docker     : {task.docker_image or '(default)'}  →  {task.docker_mount_path or '/workspace'}")
            print()
            print("── config.toml that would be written ──")
            if task.docker_image:
                print(f"[sandbox]")
                print(f'base_container_image = "{task.docker_image}"')
                print(f'workspace_mount_path_in_sandbox = "{task.docker_mount_path}"')
            else:
                print("(no custom sandbox — project not in PROJECT_DOCKER_CONFIG)")
            print()
            print("── Task prompt ──")
            print(task.task_prompt)
            print()
        print(sep)
        print(f"Total tasks: {len(tasks)}  (dry-run — nothing dispatched)")
