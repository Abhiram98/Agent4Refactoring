from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from enum import Enum

class TaskTier(str, Enum):
    MECHANIC = "mechanic"
    ARCHITECT = "architect"
    PRODUCT_OWNER = "product_owner"
    TDD = "tdd"

class TaskPrompt(BaseModel):
    """
    Representation of a single task prompt for a specific persona/tier.
    """
    prompt: str = Field(..., description="The generated instruction for the agent")
    failing_test: Optional[str] = Field(description="A failing Java test case, primarily for the TDD tier",
                                        default=None)

class RefactoringTask(BaseModel):
    """
    The structured task object containing prompts for all 4 tiers.
    Redundant repository/pattern metadata is omitted as it can be joined 
    via the task_id from aggregated_candidates.json.
    """
    task_id: str = Field(..., description="Unique task identifier matching the candidate ID")
    prompts: Dict[TaskTier, TaskPrompt] = Field(..., description="The prompts for each tier")
    
    class Config:
        use_enum_values = True
