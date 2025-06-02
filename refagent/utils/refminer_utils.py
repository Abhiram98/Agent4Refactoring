import json
import os
import pathlib
import subprocess
from pydantic import BaseModel, Field
import tempfile
from typing import Self

import refagent.refactoring_types.refactorings as refactoring_types


class RminerError(Exception):
    pass


class RefminerRunner(BaseModel):
    refminer_path: str = Field(..., description="path of refactoringminer, to execute")

    def run(self, project_path, commit_hash) -> list[refactoring_types.RefminerOut]:
        """Run refactoring miner on the specific commit
        in the specified project"""
        tmp = tempfile.NamedTemporaryFile()
        command = [
            self.refminer_path, '-c',
            project_path,
            commit_hash,  # on this commits
            '-json', tmp.name  # store output json in tempfile
        ]
        result = subprocess.run(command, stderr=subprocess.PIPE, stdout=subprocess.PIPE, timeout=60)
        if (result.returncode == 0):
            with open(tmp.name) as f:
                return refactoring_types.RefminerOut.load(json.load(f))
        else:
            raise RminerError(result.stderr.decode('utf-8'))


class RefminerCompare(BaseModel):
    pass


refminer_path = os.environ.get("REFMINER_PATH")
default_runner = RefminerRunner(refminer_path=refminer_path)
