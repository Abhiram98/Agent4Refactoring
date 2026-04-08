from pathlib import Path
from typing import List
from pydantic import BaseModel

from benchmark.design_patterns.pattern_first.models import BirthInfo
from benchmark.design_patterns.scorecard import CandidateScorecard, FilePresenceCheck, RefactoringMinerCheck


class ScoreCardCreator(BaseModel):
    repo_path: Path
    birth_info: BirthInfo

    def generate_scorecard(self) -> CandidateScorecard:
        # TODO: generate the scorecard using LLM prompts.
        self.generate_file_checks()
        return CandidateScorecard()

    def generate_file_checks(self) -> List[FilePresenceCheck]:
        # TODO: Go through the birth commit. List out the deleted/added files.
        #  Based on that information, use an LLM to filter for appropriate files which are part of the pattern.
        #  Generate the checks that the files exist or are absent.
        return []

    def generate_refminer_checks(self) -> List[RefactoringMinerCheck]:
        # TODO: Run refactoring miner on the birth commit.
        #  Pass the output to an LLM (only the descriptions of the refactorings.)
        #  Ask the LLM to filter out for the important refactorings to apply the pattern.
        #  create the required output
        return []