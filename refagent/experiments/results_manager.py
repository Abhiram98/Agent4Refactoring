import json
import os
import pathlib

default_save_path = pathlib.Path(__file__).parent.parent.parent.joinpath('data/results')

class ResultsManager:
    def __init__(self, run_identifier='default'):
        self.responses = []
        self.save_path = default_save_path.joinpath(run_identifier)
        try:
            os.makedirs(self.save_path)
        except FileExistsError:
            pass

    def add(self, ref_id, response):
        self.responses.append({
            "id": ref_id,
            "response": response
        })

    def save(self):
        with open(self.save_path.joinpath("results.json"), "w") as f:
            json.dump(self.responses, f, indent=4)
