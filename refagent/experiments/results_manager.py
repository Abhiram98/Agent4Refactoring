import json
import os
import pathlib

default_save_path = pathlib.Path(__file__).parent.parent.parent.joinpath('data/results')

class ResultsManager:
    def __init__(self, run_identifier='default', save_file="results.json"):
        self.responses = []
        self.save_path = default_save_path.joinpath(run_identifier)
        self.save_file = save_file
        try:
            os.makedirs(self.save_path)
        except FileExistsError:
            pass

        if os.path.exists(self.save_path.joinpath(self.save_file)):
            with open(self.save_path.joinpath(self.save_file)) as f:
                self.responses = json.load(f)


    def add(self, ref_id, response):
        self.responses.append({
            "id": ref_id,
            "response": response
        })

    def save(self):
        with open(self.save_path.joinpath(self.save_file), "w") as f:
            json.dump(self.responses, f, indent=4)

    def exists(self, ref_id: int):
        # checks if the ref id already exists.
        matches = [i for i in self.responses if i['id'] == ref_id]
        return len(matches) > 0

    @property
    def save_file_path(self):
        return self.save_path.joinpath(self.save_file)
