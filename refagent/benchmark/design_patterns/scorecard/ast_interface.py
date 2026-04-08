from abc import ABC, abstractmethod
from pathlib import Path


class ASTCheckEvaluator(ABC):
    """
    Base interface for dynamic AST-based structural checks.
    
    Each specific AST check (e.g., ImplementsInterfaceCheck, IsPrivateMethodCheck) 
    should inherit from this class and implement the `evaluate` method using 
    Tree-sitter.
    """

    @abstractmethod
    def evaluate(self, repo_path: Path) -> bool:
        """
        Evaluates the structural constraint against the codebase at the given commit.

        :param repo_path: The absolute path to the local git repository.
        :return: True if the AST check passes, False otherwise.
        """
        pass
