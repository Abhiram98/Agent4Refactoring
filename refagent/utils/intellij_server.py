from pydantic import BaseModel, Field
import requests
from pathlib import Path


class IntellijServer(BaseModel):
    server_url: str = Field(description="url where the server lives")

    def open_project(self, project_path: Path):
        self.call_tool("open-project", abs_project_path=str(project_path.absolute()))

    def open_file(self, rel_file_path: Path):
        self.call_tool("open-file", rel_file_path=str(rel_file_path))

    def reload_project(self):
        """Reload the project's gradle/maven things + re-indexing."""
        pass

    def call_tool(self, tool_name, **kwargs):
        """call any generic tool on the intellij server."""

        response = requests.post(f'{self.server_url}/{tool_name}', json=kwargs)
        return response.text