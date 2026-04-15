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
    Finds the class_declaration node for the given class name.
    """
    # Query looks for class declarations and captures the identifier name
    query_str = """
    (class_declaration 
        name: (identifier) @class_name
    ) @class_decl
    """
    captures = execute_query(root_node, query_str)
    
    for capture_name, nodes in captures.items():
        if capture_name == "class_name":
            for node in nodes:
                # Get the text of the identifier
                node_text = source_bytes[node.start_byte:node.end_byte].decode('utf-8')
                if node_text == target_class:
                    # In newer tree-sitter dictionary maps node to capture name, but in older it's a list of tuples.
                    # This standard handling handles the typical dictionary return (capture_name -> list of nodes)
                    # We just return the parent of this identifier which is the class declaration
                    return node.parent
                    
    # Also check interfaces
    interface_query = """
    (interface_declaration 
        name: (identifier) @interface_name
    )
    """
    captures_int = execute_query(root_node, interface_query)
    for capture_name, nodes in captures_int.items():
        if capture_name == "interface_name":
            for node in nodes:
                node_text = source_bytes[node.start_byte:node.end_byte].decode('utf-8')
                if node_text == target_class:
                    return node.parent

    return None
