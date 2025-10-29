import json
from json import JSONDecodeError
from typing import Dict, Optional, List

from pydantic.v1 import BaseModel, Field
import requests
from pathlib import Path


class IntellijServer(BaseModel):
    server_url: str = Field(description="url where the server lives")

    def open_project(self, project_path: Path):
        self.call_tool("open-project", abs_project_path=str(project_path.absolute()))

    def open_file(self, rel_file_path: Path):
        return self.call_tool("open-file", rel_file_path=str(rel_file_path))

    def create_file(self, rel_file_path: Path):
        return self.call_tool("create-file", rel_file_path=str(rel_file_path))

    def try_open_file(self, rel_file_path: Path):
        # when the caller is unsure about the path,
        # and additional searching is needed to find the right file.
        return self.call_tool("try-open-file", rel_file_path=str(rel_file_path))

    def try_create_file(self, rel_file_path: Path):
        return self.call_tool("try-create-file", rel_file_path=str(rel_file_path))

    def reload_project(self):
        """Reload the project's gradle/maven things + re-indexing."""
        return self.call_tool("wait_for_reload")

    def reset_project_reload_counters(self):
        """There are some internal counters, that keep track whether the project is in a loading state.
        Sometimes, these get deadlocked, and need to be reset. This is a workaround for other bugs.
        """
        return self.call_tool("reset_waiting")

    def call_tool(self, tool_name, **kwargs):
        """call any generic tool on the intellij server."""

        response = requests.post(f"{self.server_url}/{tool_name}", json=kwargs)
        if response.ok:
            return response.text
        else:
            return f"tool call failed - {response.status_code}: {response.text}"

    def call_tool_args(self, tool_name, *args):
        response = requests.post(f"{self.server_url}/{tool_name}", json=list(args))
        if response.ok:
            return response.text
        else:
            return f"tool call failed - {response.status_code}: {response.text}"

    def call_tool_get(self, tool_name):
        response = requests.get(f"{self.server_url}/{tool_name}")
        if response.ok:
            return response.text
        else:
            return f"tool call failed - {response.status_code}: {response.text}"

    def run_code_inspection(self, retry=2):
        for i in range(retry):
            response = requests.post(f"{self.server_url}/run_code_inspection")
            if response.status_code == 500:
                print(
                    f"code inspection failed - {response.status_code}: {response.text}"
                )
                print("retrying...")
            else:
                return response.text
        return "[]"  # code inspection failed.

    def get_file_contents(self, file_path: str) -> str:
        response = requests.get(
            f"{self.server_url}/src/get_code", json={"rel_file_path": file_path}
        )
        if response.ok:
            return response.text
        raise FileNotFoundError(f"File {file_path} not found.")

    def file_exists(self, file_path):
        try:
            self.get_file_contents(file_path)
            return True
        except FileNotFoundError:
            return False

    def get_renamed_files(self) -> Optional[Dict[str, str]]:
        """Returns a dictionary of old_name to new_name, for each renamed file."""
        try:
            renamed_files_response = json.loads(self.call_tool_get("/vcs/renamed_files"))
            renamed_files = {old_: new_ for old_, new_ in renamed_files_response}
            return renamed_files
        except JSONDecodeError as e:
            print("Failed to get a proper response from /vcs/renamed_files")
            return None

    def get_changed_files(self) -> List[str]:
        return json.loads(self.call_tool_get("/vcs/changed_files"))

    def get_changes(self) -> Dict[str, str]:
        """Returns a dict of file_path: diff"""
        return json.loads(self.call_tool_get("/vcs/changes"))
