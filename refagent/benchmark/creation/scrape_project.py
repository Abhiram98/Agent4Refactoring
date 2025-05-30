import json
import os

import langsmith
from grazie.api.client.endpoints import GrazieApiGatewayUrls
from grazie.api.client.gateway import RequestFailedException
from grazie.api.client_v2 import AuthType
from grazie_langchain_utils.language_models.grazie import ChatGrazie
from pydantic.v1 import SecretStr

import refagent
import refagent.utils.project_manager as pm
import refagent.benchmark.load as bm_load
import refagent.utils.refminer_utils as refminer
import refagent.benchmark.creation.add_gh_comments as gh
import refagent.refactoring_types.refactorings as refactoring_types

from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field, SkipValidation, PrivateAttr
from datetime import datetime, UTC, timezone
from git import Commit
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Optional, Type, Iterator, Iterable
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from typing_extensions import Annotated

from benchmark.creation.add_gh_comments import GithubPR


class CommitSummary(BaseModel):
    commit_message: str = Field(description="A commit message for the changes")
    summary: str = Field(description="A descriptions of the changes, including the motivation for the refactoring.")
    hints: List[str] = Field(description="A series of hints, giving clues about how the refactoring was performed.")



class CommitProcessor(BaseModel):
    id_counter: int = Field(description="value from which to increment the ids from", default=refagent.LAST_ID+1)
    commit: Commit = Field(description="The commit to process")
    project: pm.EvalProject = Field(description="The project to work with")
    model: Annotated[Optional[BaseModel], SkipValidation] = Field(description="Model to use to summarize the commit", default=None)
    _refactorings: List[refactoring_types.RefminerOut] = PrivateAttr(default=[])
    _filtered_refactorings: List[refactoring_types.RefminerOut] = PrivateAttr(default=[])

    class Config:
        arbitrary_types_allowed = True

    def process_commit(self) -> Optional[bm_load.BenchmarkItem]:
        print(f"Commit hash: {self.commit.hexsha}")
        print(f"Author: {self.commit.author.name} <{self.commit.author.email}>")
        print(f"Date: {datetime.fromtimestamp(self.commit.authored_date, UTC)}")
        print(f"Message: {self.commit.message}")


        # Gather additional context
        # 1. Improve the commit message
        # 2. PR comments, review comments on the code

        # filter out unrelated hunks

        # Run refactoring miner.
        self._refactorings = refminer.default_runner.run(
            project_path=self.project.get_project_path(),
            commit_hash=str(self.commit.hexsha)
        )
        if len(self._refactorings) == 0:
            return None # There are no refactorings detected by rminer, which is an odd case.
        if not self.should_analyse():
            return None

        self.compute_filtered_refactorings() # sets the value of self._filtered_refactorings
        edited_files = self.edited_files_map(self._filtered_refactorings)
        if len(edited_files) == 0:
            return None # no files were refactored.
        starting_files = max(edited_files.items(), key=lambda x: x[1])
        starting_file = starting_files[0]
        if self.model is not None:
            commit_summary = self.summarize_commit(edited_files)
        else:
            commit_summary = CommitSummary(commit_message=self.commit.message,
                                           summary="",
                                           hints=[])

        self.id_counter += 1
        print("-" * 50)

        print(commit_summary)

        return bm_load.BenchmarkItem(
                ref_id=self.id_counter,
                project_name=self.project.project_name,
                v1_hash=str(self.commit.parents[0].hexsha),
                v2_hash=str(self.commit.hexsha),
                orig_commit_message=self.commit.message,
                improved_commit_message=commit_summary.commit_message,
                change_summary=commit_summary.summary,
                hints=commit_summary.hints,
                starting_file=starting_file,
                refactoring_changes=self._refactorings,
                diffs=self.project.get_changes(self.commit.hexsha),
                pull_request=self.get_pr()
            )

    def get_pr(self) -> Optional[GithubPR]:
        comment_importer = gh.CommentImporter(project=self.project)
        try:
            return comment_importer.get_comments(
                str(self.commit.parents[0].hexsha),
                str(self.commit.hexsha)
            )
        except:
            print("Failed to get PR comments")
            return

    def edited_files_map(self, refactorings: List[refactoring_types.RefminerOut]) -> Dict[str, int]:
        """Find the most refactored file, as the starting file.
        This is a hueristic, but it should work.
        """
        refactoring_count_map = defaultdict(int)
        for r in refactorings:
            refactored_files = set()
            for loc in r.leftSideLocations:
                refactored_files.add(loc.filePath)
            
            # Count each file only once.
            for f in refactored_files:
                refactoring_count_map[f] += 1
                
        return refactoring_count_map
        # return max(refactoring_count_map.items(), key=lambda x: x[1])[0]

    def summarize_commit(self, edited_files: Dict[str, int]) -> CommitSummary:
        most_edited_files = sorted(edited_files.items(), key=lambda x: x[1], reverse=True)
        parser = PydanticOutputParser(pydantic_object=CommitSummary)
        most_edited_file_ = most_edited_files[0][0]


        system_message = SystemMessage("You look at git diffs and provide a commit message. "
                                  f"{self.get_additional_instructions()}"
                                  f"Respond in the following format: {parser.get_format_instructions()}")
        changes, diff = self.get_diff()
        try:
            response = self.model.invoke(
                [
                    system_message,
                    HumanMessage(diff)
                ]
            )
        except RequestFailedException:
            print("payload too large.")
            diff = self.get_top10_diff(changes, most_edited_files)
            response = self.model.invoke([
                    system_message,
                    HumanMessage(diff)]
            )
        commit_summary = parser.invoke(response)

        return commit_summary

    def get_top10_diff(self, changes, most_edited_files):
        top_ten_files = [f[0] for f in most_edited_files][:10]
        diff = ""
        for c in changes:
            if (c.git_diff.a_path is not None and
                    not any(x in c.git_diff.a_path for x in top_ten_files)):
                continue
            for h in c.hunks:
                diff += h.content + '\n'
        return diff

    def get_diff(self):
        changes = self.project.get_changes(self.commit.hexsha)
        diff = ""
        for c in changes:
            for h in c.hunks:
                diff += h.content + '\n'
        return changes, diff

    def should_analyse(self):
        return len(self._refactorings) > 0

    def compute_filtered_refactorings(self) -> List[refactoring_types.RefminerOut]:
        self._filtered_refactorings = self._filtered_refactorings
        return self._filtered_refactorings

    def get_additional_instructions(self) -> str:
        return ""


class Scraper(BaseModel):

    id_counter: int = Field(description="value from which to increment the ids from", default=refagent.LAST_ID + 1)
    project_name: str = Field(description="name of the project to scrape")
    cutoff_date: datetime = Field(description="cutoff date before which commits should NOT be scraped.",
                                  default=datetime(2024, 1, 1, tzinfo=UTC))
    output_path: Path = Field(description="output path to save the scraped data")
    gather_data_points: List[bm_load.BenchmarkItem] = Field(default=[])
    commit_processor: Type[CommitProcessor] = Field(description="Commit processor to use to process commits")
    commits: List[str] = Field(default=[])

    _full_benchmark: List[bm_load.BenchmarkItem] = PrivateAttr(default=[])
    limit_commits: int = Field(description="limit the number of commits to scrape", default=50)

    _previously_analysed_commits: List[str] = PrivateAttr(default=[])
    _counter: int = PrivateAttr(default=0)


    KEYWORDS: List[str] = ['refactor', 'redesign', 'reorganize', 'restructure', 'rewrite',
                           'move', 'extract', 'improve', 'split', 'rename', 'introduce', 'encapsulate',
                           'rework'] # keywords present in the commit message, to identify the change as refactoring
    # Other keyword options: clean-up, rewrite, restructure, redesign, move, extract, improve, split, reorganize, rename

    model_config = {'arbitrary_types_allowed': True}

    def get_previously_analysed(self):
        if os.path.exists(self.output_path):
            with open(self.output_path) as f:
                self.gather_data_points = bm_load.load_benchmark(
                    json.load(f)
                )
        if os.path.exists(refagent.benchmark_full_file):
            with open(refagent.benchmark_full_file) as f:
                self._full_benchmark = bm_load.load_benchmark(
                    json.load(f)
                )
        self._previously_analysed_commits = ([i.v2_hash for i in self.gather_data_points] +
                                             [i.v2_hash for i in self._full_benchmark])


    def run(self):
        self.get_previously_analysed()
        project = pm.EvalProject(project_name=self.project_name)
        # Iterate git history for commits after cutoff_data
        for commit in self.iter_commits(project):
            if (
                    datetime.fromtimestamp(commit.authored_date, UTC) >= self.cutoff_date # For some reason, even older commits are picked up.
                    and
                    (
                            str(commit.hexsha) not in self._previously_analysed_commits
                            or str(commit) in self.commits
                    )
            ):
                self.process_commit(commit, project)

                with open(self.output_path, "w") as f:
                    json.dump([i.to_json() for i in self.gather_data_points], f, indent=4)

                if self._counter >= self.limit_commits:
                    break
        print(f"successfully scraped {self._counter} data points.")

        # Append to benchmark_file

    def iter_commits(self, project) -> Iterable:
        if len(self.commits) > 0:
            return [project.git_repo.commit(commit_str) for commit_str in self.commits]
        else:
            return project.git_repo.iter_commits(since=self.cutoff_date)

    def process_commit(self, commit: Commit, project: pm.EvalProject):
        grazie_llm = ChatGrazie(grazie_jwt_token=SecretStr(os.getenv("GRAZIE_JWT_TOKEN")),
                                client_auth_type=AuthType.APPLICATION,
                                client_url=GrazieApiGatewayUrls.STAGING,
                                profile="openai-gpt-4o-mini",
                                client_agent_name='ref-agent',
                                client_agent_version='0.1'
                                )
        bench_item = self.commit_processor(
            id_counter=self.id_counter,
            commit=commit,
            project=project,
            model=grazie_llm
        ).process_commit()
        if bench_item is not None:
            self.gather_data_points.append(bench_item)
            self.id_counter += 1
            self._counter += 1



class KeywordProcessor(CommitProcessor):
    
    KEYWORDS: List[str] = ['refactor', 'redesign', 'reorganize', 'restructure', 'rewrite',
                           'move', 'extract', 'improve', 'split', 'rename', 'introduce', 'encapsulate',
                           'rework'] 

    def should_analyse(self):
        return any([k in self.commit.message.lower() for k in self.KEYWORDS])



class RenameProcessor(CommitProcessor):
    
    def contains_important_refactoring(self, refactorings: List[refactoring_types.RefminerOut]) -> bool:
        if len(refactorings) == 0:
            return False

        refactoring_count = defaultdict(int)
        unique_files = set()
        for r in refactorings:
            # if r.type in ['Extract Class', 'Extract Interface', 'Extract Superclass', 'Extract Subclass']:
            #     return True
            parent_type = r.type.split(' ')[0]
            refactoring_count[parent_type] += 1
            for loc in r.leftSideLocations:
                unique_files.add(loc.filePath)
        rename_pct = refactoring_count['Rename'] / len(refactorings)
        lots_of_renames = refactoring_count['Rename'] > 10 and len(unique_files) > 1
        high_pct_renames = rename_pct > 0.6 and refactoring_count['Rename'] > 2

        return lots_of_renames or high_pct_renames
    
    def should_analyse(self):
        return self.contains_important_refactoring(self._refactorings)

    def compute_filtered_refactorings(self) -> List[refactoring_types.RefminerOut]:
        self._filtered_refactorings = [i for i in self._refactorings
                                       if i.type.split()[0] == 'Rename']
        return self._filtered_refactorings

    def get_additional_instructions(self) -> str:

        all_renames_str = ""

        for refactoring in self._filtered_refactorings:
            all_renames_str += refactoring.description + "\n"

        return f"Please summarize the following rename refactorings: \n{all_renames_str}\n"

    def get_diff(self):

        changes = self.project.get_changes(self.commit.hexsha)
        renamed_files = [i.leftSideLocations[0].filePath for i in self._filtered_refactorings]

        diff = ""
        for c in changes:
            if c.git_diff.b_path not in renamed_files:
                continue
            for h in c.hunks:
                diff += h.content + '\n'
        return changes, diff
    
class ExtractMethodProcessor(RenameProcessor):
    
    def contains_important_refactoring(self, refactorings: List[refactoring_types.RefminerOut]) -> bool:
        if len(refactorings) == 0:
            return False

        refactoring_count = defaultdict(int)
        for r in refactorings:
            refactoring_count[r.type] += 1

        em_count = (refactoring_count['Extract Method'] +
                    refactoring_count['Parametrize Variable'] )
                    # refactoring_count['Add Parameter'] +
                    # refactoring_count['Merge Parameter']
        extract_method_pct = em_count / len(refactorings)
        return extract_method_pct > 0.6 and em_count > 2

# class CodeSmellBasedScraper(Scraper):
#     def should_analyse(self, commit: Commit):
#         project = pm.EvalProject(project_name=self.project_name)
#         refactorings = refminer.default_runner.run(
#             project_path=project.get_project_path(),
#             commit_hash=str(commit.hexsha)
#         )
#         return len(refactorings) > 0


# TODO: limit number of refactorings, types of refactorings, # of files changes. restrict to method scope

# "refactor the method <> by applying one of these refactorings <EM, MM, Rename, Inline, ...>"

if __name__ == '__main__':
    import argparse

    # Set up argument parser
    parser = argparse.ArgumentParser(description='Run different types of refactoring scrapers')
    parser.add_argument('scraper_type', choices=['keyword', 'rename', 'extract_method'],
                        help='Type of scraper to run')
    parser.add_argument('--project', default='flink', help='Project name to analyze')
    parser.add_argument('--id_counter', type=int, default=139, help='Starting ID counter')
    parser.add_argument('--commits', type=str, default='[]', help='List of commits to scrape')
    parser.add_argument('--cutoff_date', type=str, default='2024-01-01', help='Cutoff date for commits to scrape')


    args = parser.parse_args()

    # Map scraper types to classes
    scraper_map = {
        'keyword': KeywordProcessor,
        'rename': RenameProcessor,
        'extract_method': ExtractMethodProcessor
    }

    # Get the appropriate scraper class
    scraper_class = scraper_map[args.scraper_type]
    commits = args.commits.split(',')

    with langsmith.trace(name=f"scraping data for {args.project} "
                              f"using {args.scraper_type}", tags=["scrape"]) as tracer:
        os.makedirs(refagent.data_folder.joinpath(f'ref_miner/{args.scraper_type}'), exist_ok=True)
        Scraper(
            project_name=args.project,
            output_path=refagent.data_folder.joinpath(f'ref_miner/{args.scraper_type}/{args.project}.json'),
            id_counter=args.id_counter,
            commit_processor=scraper_class,
            commits=commits,
            cutoff_date=datetime.fromisoformat(args.cutoff_date).replace(tzinfo=UTC)
        ).run()
