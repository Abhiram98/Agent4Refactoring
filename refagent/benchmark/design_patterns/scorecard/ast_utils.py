from pathlib import Path
from typing import Optional, List, Tuple
import logging

logger = logging.getLogger(__name__)

try:
    import tree_sitter
    import tree_sitter_java
    HAS_TREE_SITTER = True
except ImportError:
    HAS_TREE_SITTER = False
    logger.warning("tree-sitter or tree-sitter-java not installed. AST checks will fail.")


def get_java_language():
    if not HAS_TREE_SITTER:
        raise ImportError("tree-sitter-java is not installed.")
    # tree-sitter >= 0.22.0 bindings
    return tree_sitter.Language(tree_sitter_java.language())


def parse_java_bytes(source_bytes: bytes):
    """
    Parses Java source from raw bytes (e.g., read from a git blob).
    Returns (tree, source_bytes) or (None, None) on failure.
    """
    if not HAS_TREE_SITTER:
        raise ImportError("tree-sitter is not installed.")
    try:
        language = get_java_language()
        parser = tree_sitter.Parser(language)
        tree = parser.parse(source_bytes)
        return tree, source_bytes
    except Exception as e:
        logger.error(f"Failed to parse java bytes: {e}")
        return None, None


def parse_java_file(filepath: Path):
    """
    Parses a Java file and returns the syntax tree.
    Returns None if the file could not be read or parsed.
    """
    if not HAS_TREE_SITTER:
        raise ImportError("tree-sitter is not installed.")
        
    try:
        with open(filepath, "rb") as f:
            source_content = f.read()
            
        language = get_java_language()
        parser = tree_sitter.Parser(language)
        tree = parser.parse(source_content)
        return tree, source_content
    except Exception as e:
        logger.error(f"Failed to parse java file {filepath}: {e}")
        return None, None

def execute_query(node, query_str: str):
    """
    Executes a Tree-Sitter query on a specific node and returns the captures.
    """
    language = get_java_language()
    query = language.query(query_str)
    return query.captures(node)


def find_class_declaration(root_node, source_bytes: bytes, target_class: str):
    """
    Finds the class_declaration or interface_declaration node for the given class name.
    Supports nested classes using dot notation (e.g., 'ConnectionConfiguration.Builder').
    """
    # Query for all class and interface declarations
    query_str = """
    [
      (class_declaration name: (identifier) @name)
      (interface_declaration name: (identifier) @name)
    ] @decl
    """
    captures = execute_query(root_node, query_str)
    
    # captures structure depends on tree-sitter version
    # Modern: {'name': [node, ...], 'decl': [node, ...]}
    # Old: [(node, 'name'), (node, 'decl'), ...]
    
    if isinstance(captures, dict):
        # Index nodes by their byte position to associated names with declarations
        decl_nodes = captures.get("decl", [])
        name_nodes = captures.get("name", [])
    else:
        decl_nodes = [n for n, c in captures if c == "decl"]
        name_nodes = [n for n, c in captures if c == "name"]

    # Map declaration nodes to their simple names
    decl_to_name = {}
    for d_node in decl_nodes:
        # Find the name identifier that belongs to this declaration
        for n_node in name_nodes:
            if n_node.parent == d_node:
                decl_to_name[d_node] = source_bytes[n_node.start_byte:n_node.end_byte].decode('utf-8')
                break

    def get_full_name(node):
        name = decl_to_name.get(node)
        if not name:
            return None
            
        # Walk up to find parent declarations
        curr = node.parent
        while curr:
            if curr.type in ("class_declaration", "interface_declaration"):
                parent_name = get_full_name(curr)
                if parent_name:
                    return f"{parent_name}.{name}"
            curr = curr.parent
        return name

    for d_node in decl_nodes:
        full_name = get_full_name(d_node)
        if full_name == target_class:
            return d_node

    return None
