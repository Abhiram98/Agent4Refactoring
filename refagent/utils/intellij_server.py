from pydantic.v1 import BaseModel, Field
import requests
from pathlib import Path


class IntellijServer(BaseModel):
    server_url: str = Field(description="url where the server lives")

    def open_project(self, project_path: Path):
        self.call_tool("open-project", abs_project_path=str(project_path.absolute()))

    def open_file(self, rel_file_path: Path):
        return self.call_tool("open-file", rel_file_path=str(rel_file_path))

    def reload_project(self):
        """Reload the project's gradle/maven things + re-indexing."""
        return self.call_tool('wait_for_reload')

    def call_tool(self, tool_name, **kwargs):
        """call any generic tool on the intellij server."""

        response = requests.post(f'{self.server_url}/{tool_name}', json=kwargs)
        if response.ok:
            return response.text
        else:
            return f"tool call failed - {response.status_code}: {response.text}"

    def call_tool_get(self, tool_name):
        response = requests.get(f'{self.server_url}/{tool_name}')
        if response.ok:
            return response.text
        else:
            return f"tool call failed - {response.status_code}: {response.text}"