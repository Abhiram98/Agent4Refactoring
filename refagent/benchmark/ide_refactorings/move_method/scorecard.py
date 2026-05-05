from typing import List, Dict, Any, Tuple
from pathlib import Path
import os

from refagent.utils.refminer_utils import default_runner
from refagent.benchmark.ide_refactorings.base_scorecard import BaseIdeScorecard
from .models import MoveMethodTask

class MoveMethodScorecard(BaseIdeScorecard):
    def __init__(self, task: MoveMethodTask, workspace_path: str):
        super().__init__(task, workspace_path)
        
    def _resolve_file_from_class(self, class_name: str) -> str:
        """
        Attempts to resolve a fully qualified class name to a file path within the workspace.
        This simply converts org.apache.Foo to org/apache/Foo.java and deeply searches for it.
        """
        parts = class_name.split('.')
        # In case it's an inner class like "Foo.Bar", we just bound to the outer class file "Foo.java"
        # We can try replacing dots with slashes
        path_suffix = "/".join(parts) + ".java"
        
        # We can also do a glob search in the workspace to find a file ending with this specific path
        # Fallback to just returning the last segment + .java if full path isn't strictly mapping.
        # But for Move Method, usually the full package path is exactly the directory structure in src/main/java.
        search_target = "/".join(parts) 
        
        # Heuristic: search workspace for files matching *parts[-1].java
        import glob
        matches = glob.glob(f"{self.workspace_path}/**/*{parts[-1]}.java", recursive=True)
        if matches:
            # Prefer the one matching the deepest package structure
            for m in matches:
                if "/".join(parts[:-1]) in m:
                    return os.path.relpath(m, self.workspace_path)
            return os.path.relpath(matches[0], self.workspace_path)
        return ""
        
    def resolve_file_paths(self) -> Tuple[str, str]:
        source_file = self._resolve_file_from_class(self.task.source_class)
        target_file = self._resolve_file_from_class(self.task.target_class)
        return source_file, target_file

    def check_refactoring_miner(self) -> bool:
        try:
            rm_refactorings = default_runner.run(
                project_path=self.workspace_path, 
                commit_hash="HEAD"
            )
        except Exception as e:
            print(f"RefactoringMiner execution failed: {e}")
            return False
            
        for op in rm_refactorings:
            op_type = op.type if hasattr(op, "type") else op.get("type", "")
            op_desc = op.description if hasattr(op, "description") else op.get("description", "")
            
            # The agent is starting with an already-extracted method and just moving it,
            # so the expected refactoring is 'Move Method'.
            if op_type == "Move Method":
                # Ensure the method name and target class correspond to what was requested
                if self.task.method_name in op_desc and self.task.target_class in op_desc:
                    return True
                    
            elif op_type in ["Move And Rename Method", "Extract And Move Method"]:
                # If they did something slightly different but still achieved the move
                if self.task.method_name in op_desc and self.task.target_class in op_desc:
                    return True
                    
        return False
        
    def check_blast_radius(self) -> dict:
        source_file, target_file = self.resolve_file_paths()
        
        target_files = []
        if source_file: target_files.append(source_file)
        if target_file and target_file not in target_files: target_files.append(target_file)
        
        return self.calculate_blast_radius(
            base_commit=self.task.base_commit,
            target_files=target_files,
            ignored_methods=[self.task.method_name]
        )

    def evaluate(self) -> Dict[str, Any]:
        rm_passed = self.check_refactoring_miner()
        blast_radius = self.check_blast_radius()
        tests_passed = self.run_tests()
        
        # A Move Method is successful if RM reports the move, tests pass,
        # and no unrelated methods were manipulated inside the touched classes.
        final_pass = rm_passed and tests_passed and (blast_radius.get("unrelated_methods_modified", 0) == 0)
        
        self.metrics = {
            "task_id": self.task.id,
            "refactoring_miner_passed": rm_passed,
            "tests_passed": tests_passed,
            "blast_radius": blast_radius,
            "final_pass": final_pass
        }
        return self.metrics
