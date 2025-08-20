from pydantic.v1 import BaseModel, Field
from typing import List, Optional, Dict
import refagent.refactoring_types.refactorings as refactoring_types
import refagent.agents.refactrix.supported_refactorings as sup_refs
from pathlib import Path
import re


class CritiqueResult(BaseModel):
    """Result of critiquing a refactoring suggestion against oracle data."""
    is_valid: bool = Field(description="Whether the suggestion matches oracle expectations")
    confidence_score: Optional[float] = Field(description="Confidence in the validation (0.0-1.0)", default=None)
    oracle_match: Optional[refactoring_types.RefminerOut] = Field(description="Matching oracle entry if found", default=None)
    feedback: str = Field(description="Feedback message for the LLM", default="")
    reason: str = Field(description="Detailed reason for the validation result", default="")

    class Config:
        arbitrary_types_allowed = True


class CritiqueConfig(BaseModel):
    """Configuration for the critique component."""
    enabled: bool = Field(description="Whether critique is enabled", default=True)
    strict_new_name_validation: bool = Field(description="Validate both old and new names", default=False)
    line_tolerance: int = Field(description="Line number tolerance (±N lines)", default=2)
    max_critique_retries: int = Field(description="Maximum retries after critique failure", default=3)


class CritiqueComponent(BaseModel):
    """Component that validates refactoring suggestions against oracle data."""
    oracle_data: List[refactoring_types.RefminerOut] = Field(description="Oracle refactoring data for validation")
    current_file: str = Field(description="File being refactored (relative path)")
    config: CritiqueConfig = Field(description="Critique configuration", default_factory=CritiqueConfig)
    
    class Config:
        arbitrary_types_allowed = True

    def validate_rename_suggestion(self, old_name: str, new_name: str, 
                                 line_num: int, code_element_type: str) -> CritiqueResult:
        """
        Validate if the suggested rename matches oracle expectations.
        
        Args:
            old_name: The current name to be renamed
            new_name: The proposed new name
            line_num: Line number where the rename should occur
            code_element_type: Type of code element ('variable', 'method', 'class', etc.)
            
        Returns:
            CritiqueResult indicating validation outcome
        """
        if not self.config.enabled:
            return CritiqueResult(
                is_valid=True, 
                feedback="Critique disabled - allowing all suggestions",
                reason="Critique component is disabled"
            )
        
        # Find matching oracle entries
        matching_entries = self._find_matching_oracle_entries(
            old_name, new_name, line_num, code_element_type
        )
        
        if not matching_entries:
            return CritiqueResult(
                is_valid=False,
                feedback=f"No oracle match found for renaming '{old_name}' to '{new_name}' at line {line_num}. "
                        f"Expected refactorings in this file: {self._get_expected_renames_summary()}",
                reason=f"No oracle entry matches the suggested rename: {old_name} → {new_name} at line {line_num}"
            )
        
        # Find best match
        best_match = self._select_best_match(matching_entries, old_name, new_name, line_num)
        temp = best_match
        
        # if self.config.strict_new_name_validation:
        #     # Validate both old and new names
        #     oracle_new_name = self._extract_name_from_code_element(best_match.rightSideLocations[0])
        #     if oracle_new_name != new_name:
        #         return CritiqueResult(
        #             is_valid=False,
        #             oracle_match=best_match,
        #             feedback=f"Oracle expects '{old_name}' to be renamed to '{oracle_new_name}', "
        #                     f"but you suggested '{new_name}'. Please use the expected name.",
        #             reason=f"New name mismatch: expected '{oracle_new_name}', got '{new_name}'"
        #         )
        
        return CritiqueResult(
            is_valid=True,
            oracle_match=best_match,
            feedback=f"Valid rename suggestion: '{old_name}' → '{new_name}' matches oracle expectations",
            reason=f"Successfully matched oracle entry at line {best_match.leftSideLocations[0].startLine}"
        )

    def _find_matching_oracle_entries(self, old_name: str, new_name: str, 
                                    line_num: int, code_element_type: str) -> List[refactoring_types.RefminerOut]:
        """Find oracle entries that match the suggestion criteria."""
        matching_entries = []
        
        for oracle_entry in self.oracle_data:
            if self._matches_oracle_entry(oracle_entry, old_name, new_name, line_num, code_element_type):
                matching_entries.append(oracle_entry)
        
        return matching_entries

    def _matches_oracle_entry(self, oracle_entry: refactoring_types.RefminerOut, 
                             old_name: str, new_name: str, line_num: int, code_element_type: str) -> bool:
        """Check if an oracle entry matches the suggestion criteria."""
        
        # 1. Check if it's a rename refactoring
        if not isinstance(oracle_entry, refactoring_types.Rename):
            return False
        
        # 2. File path match - normalize paths for comparison
        oracle_file = oracle_entry.leftSideLocations[0].filePath
        if not self._files_match(oracle_file, self.current_file):
            return False
        
        # 3. Line number proximity
        # oracle_line = oracle_entry.leftSideLocations[0].startLine
        # if abs(oracle_line - line_num) > self.config.line_tolerance:
        #     return False

        oracle_start_line = oracle_entry.leftSideLocations[0].startLine
        oracle_end_line = oracle_entry.leftSideLocations[0].endLine
        
        # Check if suggested line is within oracle range (no tolerance for now)
        if code_element_type == "method":
            if not (oracle_start_line <= line_num <= oracle_end_line):
                return False
        else:
            if oracle_start_line != line_num:
                return False
        
        # 4. Code element type match
        # oracle_type = oracle_entry.type.lower().split(" ")[-1].strip()
        # if oracle_type != code_element_type.lower().strip():
        #     return False
        
        # 5. Old name approx match
        oracle_old_name = self._extract_name_from_code_element(oracle_entry.leftSideLocations[0])
        # if oracle_old_name != old_name:
        #     return False
        if old_name not in oracle_old_name:
            return False
        
        return True

    def _select_best_match(self, matching_entries: List[refactoring_types.RefminerOut], 
                          old_name: str, new_name: str, line_num: int) -> refactoring_types.RefminerOut:
        """Select the best matching oracle entry from candidates."""
        if len(matching_entries) == 1:
            return matching_entries[0]
        
        # Score each match based on line number proximity
        scored_matches = []
        for entry in matching_entries:
            oracle_line = entry.leftSideLocations[0].startLine
            line_distance = abs(oracle_line - line_num)
            score = 1.0 / (1.0 + line_distance)  # Higher score for closer lines
            scored_matches.append((score, entry))
        
        # Return entry with highest score
        scored_matches.sort(key=lambda x: x[0], reverse=True)
        return scored_matches[0][1]

    def _files_match(self, oracle_file: str, current_file: str) -> bool:
        """Check if file paths match, handling different path formats."""
        # Normalize paths by converting to Path objects and comparing
        oracle_path = Path(oracle_file)
        current_path = Path(current_file)
        
        # Compare as strings after normalization
        return str(oracle_path) == str(current_path) or oracle_path.name == current_path.name

    # def _code_element_types_match(self, oracle_type: str, suggested_type: str) -> bool:
    #     """Check if code element types match, handling different naming conventions."""
    #     # Mapping from tool types to oracle types
    #     type_mapping = {
    #         'variable': ['VARIABLE_DECLARATION', 'LOCAL_VARIABLE', 'FIELD'],
    #         'field': ['FIELD', 'ATTRIBUTE', 'VARIABLE_DECLARATION'],
    #         'method': ['METHOD_DECLARATION', 'METHOD'],
    #         'class': ['CLASS_DECLARATION', 'CLASS'],
    #         'parameter': ['PARAMETER', 'FORMAL_PARAMETER']
    #     }
    #
    #     suggested_lower = suggested_type.lower()
    #     oracle_upper = oracle_type.upper()
    #
    #     # Direct match
    #     if suggested_lower == oracle_upper.lower():
    #         return True
    #
    #     # Check mapping
    #     if suggested_lower in type_mapping:
    #         return oracle_upper in type_mapping[suggested_lower]
    #
    #     return False

    def _extract_name_from_code_element(self, location: refactoring_types.CodeLocation) -> str:
        """Extract the identifier name from a code element string."""
        code_element = location.codeElement
        if not code_element:
            return ""
        
        # Handle different code element formats
        # Format: "name : type" for variables/parameters
        if " : " in code_element:
            return code_element.split(" : ")[0].strip()
        
        # Format: "public void methodName(...)" for methods
        if location.codeElementType in ['METHOD_DECLARATION', 'METHOD']:
            # Extract method name using regex
            method_match = re.search(r'\b(\w+)\s*\(', code_element)
            if method_match:
                return method_match.group(1)
        
        # Format: "class ClassName" for classes
        if location.codeElementType in ['CLASS_DECLARATION', 'CLASS']:
            class_match = re.search(r'\bclass\s+(\w+)', code_element)
            if class_match:
                return class_match.group(1)
        
        # Fallback: return the whole element
        return code_element.strip()

    def _get_expected_renames_summary(self) -> str:
        """Get a summary of expected renames in the current file for feedback."""
        file_renames = []
        for oracle_entry in self.oracle_data:
            if (isinstance(oracle_entry, refactoring_types.Rename) and 
                self._files_match(oracle_entry.leftSideLocations[0].filePath, self.current_file)):
                
                old_name = self._extract_name_from_code_element(oracle_entry.leftSideLocations[0])
                new_name = self._extract_name_from_code_element(oracle_entry.rightSideLocations[0])
                line_num = oracle_entry.leftSideLocations[0].startLine
                file_renames.append(f"'{old_name}' → '{new_name}' at line {line_num}")
        
        if not file_renames:
            return "No rename refactorings expected in this file"
        
        return ", ".join(file_renames[:3]) + ("..." if len(file_renames) > 3 else "")