import json
from json import JSONDecodeError

import refagent
import refagent.agents.refactrix.review.critique as critique
import refagent.agents.refactrix.analysis.scope as scope
import refagent.agents.refactrix.rename_suggestions as rename_suggestions
import refagent.utils.intellij_server as ij


class HumanValidator(critique.CritiqueComponent):

    def validate_suggestion(
        self, suggestion: rename_suggestions.RenameSuggestionValidated, rel_file_path
    ) -> critique.CritiqueResult:
        suggestion_dict = json.loads(suggestion.json())
        suggestion_dict.pop("reason")
        suggestion_dict.pop("llm_start_line_num")
        response_str = self.ij_server.call_tool_args("/review/renames", suggestion_dict)
        try:
            response_json = json.loads(response_str)
            return critique.CritiqueResult(
                is_valid=response_json[0], feedback="", reason=""
            )
        except IndexError as e:
            return critique.CritiqueResult(is_valid=False)
        except JSONDecodeError as e:
            print("Failed to decode json response from human review.")
            return critique.CritiqueResult(is_valid=False)

    def review_scope(self, _new_scope: scope.RenameScope) -> scope.RenameScope:
        response = self.ij_server.call_tool(
            "review/scope", pattern=_new_scope.pattern, condition=_new_scope.condition
        )
        json_response = json.loads(response)
        self.ij_server.call_tool("review/noop")
        return scope.RenameScope(**json_response)

    @property
    def ij_server(self) -> ij.IntellijServer:
        return ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
