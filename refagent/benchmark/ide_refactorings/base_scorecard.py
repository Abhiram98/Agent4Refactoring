import subprocess
from typing import List, Dict, Any
from pathlib import Path

from refagent.benchmark.design_patterns.scorecard.ast_utils import parse_java_bytes, execute_query

class BaseIdeScorecard:
    def __init__(self, task: Any, workspace_path: str):
        self.task = task
        self.workspace_path = workspace_path
        self.metrics: Dict[str, Any] = {}
        
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
            n_node = name_nodes[i]
            b_node = body_nodes[i]
            m_name = source_bytes[n_node.start_byte:n_node.end_byte].decode("utf-8")
            m_body = source_bytes[b_node.start_byte:b_node.end_byte]
            
            methods[m_name] = m_body
        return methods

    def calculate_blast_radius(self, base_commit: str, target_files: List[str], ignored_methods: List[str]) -> dict:
        """ Calculates blast radius via text (file churn) and AST (unrelated method changes). """
        metrics = {
            "files_modified": -1,
            "unrelated_methods_modified": 0
        }
        
        try:
            # 1. File churn
            diff_cmd = ["git", "diff", "--name-only", f"{base_commit}..HEAD"]
            output = subprocess.check_output(diff_cmd, cwd=self.workspace_path).decode('utf-8')
            modified_files = [f for f in output.split("\n") if f.strip()]
            metrics["files_modified"] = len(modified_files)
        except Exception as e:
            print(f"Failed to calculate git diff file churn: {e}")

        # 2. Unrelated Method Modification
        # We loop over all target files where the refactoring was expected to touch.
        # If the refactoring mutated methods inside these files that weren't the target method, we penalize.
        for target_file in target_files:
            try:
                old_file_cmd = ["git", "show", f"{base_commit}:{target_file}"]
                try:
                    old_source = subprocess.check_output(old_file_cmd, cwd=self.workspace_path, stderr=subprocess.DEVNULL)
                except subprocess.CalledProcessError:
                    # File might not exist in old commit yet
                    old_source = b""
                
                old_tree, old_src = parse_java_bytes(old_source) if old_source else (None, None)
                
                post_file_path = Path(self.workspace_path) / target_file
                if not post_file_path.exists():
                    continue
                    
                with open(post_file_path, "rb") as f:
                    new_source = f.read()
                new_tree, new_src = parse_java_bytes(new_source)
                
                if old_tree and new_tree:
                    old_methods = self._extract_methods_map(old_tree, old_source)
                    new_methods = self._extract_methods_map(new_tree, new_source)
                    
                    for m_name, old_body in old_methods.items():
                        if m_name in ignored_methods:
                            continue
                            
                        new_body = new_methods.get(m_name)
                        if new_body and old_body != new_body:
                            metrics["unrelated_methods_modified"] += 1
                            
            except Exception as e:
                print(f"Failed to calculate unrelated method mutations in {target_file}: {e}")
                
        return metrics

    def run_tests(self) -> bool:
        """Placeholder to run the project's test suite and return success."""
        # Typically maps to project_build.json in live environments
        return True
