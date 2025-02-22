import json

import refagent
import refagent.utils.project_manager as pm
import refagent.benchmark.load as benchmark
import refagent.utils.refminer_utils as refminer

import argparse
from pydantic import BaseModel, Field
from datetime import datetime, UTC
from git import Commit
from pathlib import Path


class Scraper(BaseModel):

    project_name: str = Field(description="name of the project to scrape")
    cutoff_date: datetime = Field(description="cutoff date before which commits should NOT be scraped.",
                                  default=datetime(2024, 1, 1, tzinfo=UTC))
    output_path: Path = Field(description="output path to save the scraped data")
    gather_data_points: list[benchmark.BenchmarkItem] = Field(default=[])
    id_counter: int = Field(description="value from which to increment the ids from", default=refagent.LAST_ID+1)

    KEYWORDS: list[str] = ['refactor', 'redesign', 'reorganize', 'restructure', 'rewrite'] # keywords present in the commit message, to identify the change as refactoring
    # Other keword options: clean-up, rewrite, restructure, redesign, move, extract, improve, split, reorganize, rename

    model_config = {'arbitrary_types_allowed': True}

    def run(self):
        project = pm.EvalProject(project_name=self.project_name)
        # Iterate git history for commits after cutoff_data
        count = 0
        for commit in project.git_repo.iter_commits(since=self.cutoff_date):
            if (datetime.fromtimestamp(commit.authored_date, UTC) >= self.cutoff_date # For some reason, even older commits are picked up.
                    and any([k in commit.message.lower() for k in self.KEYWORDS])):
                count += 1
                self.process_commit(commit, project)

                with open(self.output_path, "w") as f:
                    json.dump([i.to_json() for i in self.gather_data_points], f, indent=4)
        print(f"successfully scraped {count} data points.")

        # Append to benchmark_file

    def process_commit(self, commit: Commit, project: pm.EvalProject):
        print(f"Commit hash: {commit.hexsha}")
        print(f"Author: {commit.author.name} <{commit.author.email}>")
        print(f"Date: {datetime.fromtimestamp(commit.authored_date, UTC)}")
        print(f"Message: {commit.message}")


        # Gather additional context
        # 1. Improve the commit message
        # 2. PR comments, review comments on the code

        # filter out unrelated hunks

        # Run refactoring miner.
        refactorings = refminer.default_runner.run(
            project_path=project.get_project_path(),
            commit_hash=str(commit.hexsha)
        )
        if len(refactorings) == 0:
            return  # There are no refactorings detected by rminer, which is an odd case.
        left = refactorings[0].leftSideLocations
        if len(left):
            starting_file = left[0].filePath  # TODO: this is a faux starting path.
        else:
            starting_file = ''
                                                                       #  Maybe there are other files

        self.gather_data_points.append(
            benchmark.BenchmarkItem(
                ref_id=self.id_counter,
                project_name=project.project_name,
                v1_hash=str(commit.parents[0].hexsha),
                v2_hash=str(commit.hexsha),
                intent="UNKNOWN",  # TODO: figure out the intent - why the refactoring took place
                                   #  (DESIGN, COSMETIC, API_MIGRATION, ...)
                necessary_context=commit.message,  # TODO: Improve upon the commit message.
                hint=commit.message,  # TODO: get real hints by using code-review context.
                starting_files=[starting_file],  # TODO: Figure out the most impacted files.
                changes=refactorings,
                diffs=project.get_changes(commit.hexsha)
            )
        )
        self.id_counter += 1
        print("-" * 50)


if __name__ == '__main__':
    Scraper(project_name='kafka',
            output_path=refagent.data_folder.joinpath('ref_miner/kafka.json'),
            id_counter=89
            ).run()