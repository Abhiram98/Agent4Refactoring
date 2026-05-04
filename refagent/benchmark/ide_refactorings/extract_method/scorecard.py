import subprocess
from typing import List, Dict, Any, Tuple
from pathlib import Path

from refagent.utils.refminer_utils import default_runner
from refagent.benchmark.design_patterns.scorecard.ast_utils import parse_java_file, execute_query, parse_java_bytes
from .models import ExtractMethodTask

class ExtractMethodScorecard:
    def __init__(self, task: ExtractMethodTask, workspace_path: str):
        self.task = task
        self.workspace_path = workspace_path
        self.metrics: Dict[str, Any] = {}
        
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
                    # Check that the line numbers match with the oracle using a tolerance.
                    left_side = op.leftSideLocations if hasattr(op, "leftSideLocations") else op.get("leftSideLocations", [])
                    filename_basename = Path(self.task.oracle.filename).name
                    
                    for loc in left_side:
                        file_path = loc.filePath if hasattr(loc, "filePath") else loc.get("filePath", "")
                        # Make sure we're looking at the right file
                        if filename_basename in file_path:
                            start = loc.startLine if hasattr(loc, "startLine") else loc.get("startLine", 0)
                            end = loc.endLine if hasattr(loc, "endLine") else loc.get("endLine", 0)
                            
                            # Tolerance of 2 lines to account for minor agent drifts
                            if abs(start - self.task.oracle.line_start) <= 2 and abs(end - self.task.oracle.line_end) <= 2:
                                return True
                    
                    # If we fallback to strict RM name match alone because locations don't track well
                    # We might still return True if we're feeling lenient, but we mandate line verification here.
        return False
        
    def _extract_methods_map(self, tree, source_bytes: bytes) -> Dict[str, bytes]:
        """Extracts a map of {method_name: method_body_bytes} from a Java AST."""
        query_str = "(method_declaration name: (identifier) @name body: (block) @body)"
        captures = execute_query(tree.root_node, query_str)
        
        methods = {}
        if isinstance(captures, dict):
            name_nodes = captures.get("name", [])
            body_nodes = captures.get("body", [])
        else:
            name_nodes = [n for n, c in captures if c == "name"]
            body_nodes = [n for n, c in captures if c == "body"]
            
        for i in range(min(len(name_nodes), len(body_nodes))):
            # For simplicity, we assume zip aligns them safely 
            # (a strict AST query might map 1:1 if structured carefully)
            # Tree-sitter results usually preserve order of captures if there's no mismatch
            # But the better way is to iterate parent `method_declaration` and find matching names inside.
            # Alternatively, since we just want a rough heuristic of changed methods, we'll map all captured bodies to captured names.
            n_node = name_nodes[i]
            b_node = body_nodes[i]
            m_name = source_bytes[n_node.start_byte:n_node.end_byte].decode("utf-8")
            m_body = source_bytes[b_node.start_byte:b_node.end_byte]
            
            methods[m_name] = m_body
        return methods

    def check_blast_radius(self) -> dict:
        """ Calculates blast radius via text (file churn) and AST (unrelated method changes). """
        metrics = {
            "files_modified": -1,
            "unrelated_methods_modified": 0
        }
        
        try:
            # 1. File churn
            diff_cmd = ["git", "diff", "--name-only", f"{self.task.commit}..HEAD"]
            output = subprocess.check_output(diff_cmd, cwd=self.workspace_path).decode('utf-8')
            modified_files = [f for f in output.split("\n") if f.strip()]
            metrics["files_modified"] = len(modified_files)
        except Exception as e:
            print(f"Failed to calculate git diff file churn: {e}")

        # 2. Unrelated Method Modification
        target_file = self.task.oracle.filename
        try:
            old_file_cmd = ["git", "show", f"{self.task.commit}:{target_file}"]
            old_source = subprocess.check_output(old_file_cmd, cwd=self.workspace_path)
            old_tree, old_src = parse_java_bytes(old_source)
            
            post_file_path = Path(self.workspace_path) / target_file
            if not post_file_path.exists():
                return metrics
                
            with open(post_file_path, "rb") as f:
                new_source = f.read()
            new_tree, new_src = parse_java_bytes(new_source)
            
            if old_tree and new_tree:
                old_methods = self._extract_methods_map(old_tree, old_source)
                new_methods = self._extract_methods_map(new_tree, new_source)
                
                for m_name, old_body in old_methods.items():
                    # Ignore the host and extracted methods
                    if m_name == self.task.host_method_name or m_name == self.task.extracted_method_name:
                        continue
                        
                    new_body = new_methods.get(m_name)
                    if new_body and old_body != new_body:
                        # An unrelated method was changed!
                        metrics["unrelated_methods_modified"] += 1
                        
        except Exception as e:
            print(f"Failed to calculate unrelated method mutations: {e}")
            
        return metrics

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
        
        # Iterate over method declarations
        for d_node in decl_nodes:
            # Find the name node belonging to this declaration
            for n_node in name_nodes:
                if n_node.parent == d_node:
                    m_name = source_bytes[n_node.start_byte:n_node.end_byte].decode('utf-8')
                    if m_name == self.task.host_method_name:
                        # Found a host method declaration, check its body for method_invocation
                        inv_query = "(method_invocation name: (identifier) @name) @inv"
                        
                        # Tree-sitter Java query for specific node
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
        
    def run_tests(self) -> bool:
        """Placeholder to run the project's test suite and return success."""
        return True
        
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
