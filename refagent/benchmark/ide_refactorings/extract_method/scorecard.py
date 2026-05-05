from typing import List, Dict, Any, Tuple
from pathlib import Path

from refagent.utils.refminer_utils import default_runner
from refagent.benchmark.design_patterns.scorecard.ast_utils import parse_java_file, execute_query
from refagent.benchmark.ide_refactorings.base_scorecard import BaseIdeScorecard
from .models import ExtractMethodTask

class ExtractMethodScorecard(BaseIdeScorecard):
    def __init__(self, task: ExtractMethodTask, workspace_path: str):
        super().__init__(task, workspace_path)
        
    def check_refactoring_miner(self) -> bool:
        """Run RefactoringMiner to see if extraction occurred"""
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
            
            if op_type == "Extract Method":
                if self.task.extracted_method_name in op_desc:
                    left_side = op.leftSideLocations if hasattr(op, "leftSideLocations") else op.get("leftSideLocations", [])
                    filename_basename = Path(self.task.oracle.filename).name
                    
                    for loc in left_side:
                        file_path = loc.filePath if hasattr(loc, "filePath") else loc.get("filePath", "")
                        if filename_basename in file_path:
                            start = loc.startLine if hasattr(loc, "startLine") else loc.get("startLine", 0)
                            end = loc.endLine if hasattr(loc, "endLine") else loc.get("endLine", 0)
                            
                            if abs(start - self.task.oracle.line_start) <= 2 and abs(end - self.task.oracle.line_end) <= 2:
                                return True
        return False

    def check_blast_radius(self) -> dict:
        return self.calculate_blast_radius(
            base_commit=self.task.commit,
            target_files=[self.task.oracle.filename],
            ignored_methods=[self.task.host_method_name, self.task.extracted_method_name]
        )

    def check_call_site_modified(self) -> bool:
        """Parses AST to ensure the host method calls the extracted method."""
        target_file = Path(self.workspace_path) / self.task.oracle.filename
        if not target_file.exists():
            return False
            
        tree, source_bytes = parse_java_file(target_file)
        if not tree:
            return False
            
        method_query = "(method_declaration name: (identifier) @name body: (block) @body) @decl"
        captures = execute_query(tree.root_node, method_query)
        
        if isinstance(captures, dict):
            decl_nodes = captures.get("decl", [])
            name_nodes = captures.get("name", [])
        else:
            decl_nodes = [n for n, c in captures if c == "decl"]
            name_nodes = [n for n, c in captures if c == "name"]
        
        for d_node in decl_nodes:
            for n_node in name_nodes:
                if n_node.parent == d_node:
                    m_name = source_bytes[n_node.start_byte:n_node.end_byte].decode('utf-8')
                    if m_name == self.task.host_method_name:
                        inv_query = "(method_invocation name: (identifier) @name) @inv"
                        
                        inv_captures = execute_query(d_node, inv_query)
                        if isinstance(inv_captures, dict):
                            inv_name_nodes = inv_captures.get("name", [])
                        else:
                            inv_name_nodes = [cn for cn, cc in inv_captures if cc == "name"]
                            
                        for inv_node in inv_name_nodes:
                            inv_name = source_bytes[inv_node.start_byte:inv_node.end_byte].decode('utf-8')
                            if inv_name == self.task.extracted_method_name:
                                return True
        return False
        
    def evaluate(self) -> Dict[str, Any]:
        """Evaluates the entire scorecard."""
        rm_passed = self.check_refactoring_miner()
        blast_radius = self.check_blast_radius()
        call_site_passed = self.check_call_site_modified()
        tests_passed = self.run_tests()
        
        final_pass = rm_passed and tests_passed and call_site_passed and (blast_radius["unrelated_methods_modified"] == 0)
        
        self.metrics = {
            "task_id": self.task.id,
            "refactoring_miner_passed": rm_passed,
            "call_site_modified": call_site_passed,
            "tests_passed": tests_passed,
            "blast_radius": blast_radius,
            "final_pass": final_pass
        }
        return self.metrics
