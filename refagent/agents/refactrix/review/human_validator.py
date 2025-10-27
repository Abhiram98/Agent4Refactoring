import json
from json import JSONDecodeError

import refagent
import refagent.agents.refactrix.review.critique as critique
from agents.refactrix.analysis.scope import RenameScope
from agents.refactrix.rename_suggestions import RenameSuggestionValidated
from agents.refactrix.review.critique import CritiqueResult
import refagent.utils.intellij_server as ij


class HumanValidator(critique.CritiqueComponent):

    def validate_suggestion(self, suggestion: RenameSuggestionValidated, rel_file_path) -> CritiqueResult:
        suggestion_dict = json.loads(suggestion.json())
        suggestion_dict.pop('reason')
        suggestion_dict.pop('llm_start_line_num')
        response_str = self.ij_server.call_tool_args('/review/renames', suggestion_dict)
        try:
            response_json = json.loads(response_str)
            return CritiqueResult(is_valid=response_json[0], feedback="", reason="")
        except IndexError as e:
            return CritiqueResult(is_valid=False)
        except JSONDecodeError as e:
            print("Failed to decode json response from human review.")
            return CritiqueResult(is_valid=False)

    def review_scope(self, _new_scope: RenameScope) -> RenameScope:
        response = self.ij_server.call_tool('review/scope', pattern=_new_scope.pattern, condition=_new_scope.condition)
        json_response = json.loads(response)
        return RenameScope(**json_response)


    @property
    def ij_server(self) -> ij.IntellijServer:
        return ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)