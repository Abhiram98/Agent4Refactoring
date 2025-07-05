import json

from langchain_openai import ChatOpenAI
from slack_sdk import WebClient

import refagent
import sys
import refagent.benchmark.load as bm_load
import refagent.refactoring_types.refactorings as refactorings
import refagent.agents.refactrix.patch_curation_agent as patch_curation_agent
import refagent.agents.refactrix.analysis as analysis
import refagent.agents.refactrix.planning as planning
import refagent.utils.intellij_server as ij
from typing import List
import refagent.utils.project_manager as pm
from datetime import datetime, UTC, timedelta
import os
from pathlib import Path

from pydantic import BaseModel, Field

class PatchCurator(BaseModel):
    data_file_path: str= Field(description="path to the data file to look at")
    should_run_agent: bool = Field(description="whether to run the agent")

    previously_analysed: List[str] = []
    agent_output: List = []
    cache_path: Path = refagent.data_folder.joinpath("monitoring/previously_analysed_for_patches.json")
    agent_output_path: Path = refagent.data_folder.joinpath("monitoring/agent_output.json")

    def load_previously_analysed(self):
        if os.path.exists(self.cache_path):
            with open(self.cache_path) as f:
                self.previously_analysed += json.load(f)
        if os.path.exists(self.agent_output_path):
            with open(self.agent_output_path) as f:
                self.agent_output += json.load(f)


    def main(self):
        '''This script finds data from the monitoring results which are suitable to submit patches,
        and runs the agent where possible'''
        # monitor_results.jsonl
        self.load_previously_analysed()
        new_renames = self.find_new_data()
        print(f"New patch opportunities found: {len(new_renames)=}")
        if self.should_run_agent:
            possible_patches = self.run_agent(new_renames)

    def find_new_data(self):
        LAST_X = 300  # only analyse the last 300 entries in the
        with open(self.data_file_path) as f:
            data = [json.loads(i) for i in f.read().splitlines()[-LAST_X:]]
            rename_data = bm_load.load_benchmark(data)
        with open(refagent.data_folder.joinpath("monitoring/for_patches.json")) as f:
            previous_data = json.load(f)
        filtered_renames: List[bm_load.BenchmarkItem] = []
        filtered_renames += bm_load.load_benchmark(previous_data)
        for i in rename_data:
            print(f"processing item {i.ref_id}")
            if any(i.ref_id == k.ref_id for k in filtered_renames):
                print("previously processed item")
                continue
            i.refactoring_changes = [r for r in i.refactoring_changes if isinstance(r, refactorings.Rename)]
            fun_refactorings = [r for r in i.refactoring_changes if
                                isinstance(r, refactorings.Rename) and r.has_type_change == False]
            project = pm.EvalProject(i.project_name)
            # project.checkout_main()
            # project.pull_project()

            try:
                commit = project.git_repo.commit(i.v2_hash)
            except:
                continue
            if (10 >= len(fun_refactorings) > 0
                    and commit.committed_datetime
                    > datetime.now(UTC) - timedelta(days=7)):
                filtered_renames.append(i)
        for r in filtered_renames:
            fun_refactorings = [r1 for r1 in r.refactoring_changes if
                                isinstance(r1, refactorings.Rename) and r1.has_type_change == False]
            f1 = fun_refactorings[0]
            r.improved_commit_message = f"{f1.type}: `{f1.old_name}` -> `{f1.new_name}` on line {f1.start_line}"
        with open(refagent.data_folder.joinpath("monitoring/for_patches.json"), 'w') as f:
            json.dump([i.to_json() for i in filtered_renames], f, indent=4)
        no_replication_fake_commits = []
        for i in filtered_renames:
            no_replication_fake_commits.append(
                {
                    "id": i.ref_id,
                    "response": {
                        "changes": [],
                        "commit_hash": i.v2_hash,
                        "trajectory": [],
                        "performed_refactorings": {}
                    }
                }
            )
        with open(refagent.data_folder.joinpath("results/patches-june-9/no-replication.json"), 'w') as f:
            json.dump(no_replication_fake_commits, f, indent=4)

        return self.get_renames_in_last_week(filtered_renames) # return new names to run the agent on.


    def get_renames_in_last_week(self, renames: List[bm_load.BenchmarkItem]) -> List[bm_load.BenchmarkItem]:
        filtered_renames: List[bm_load.BenchmarkItem] = []
        for i in renames:
            project = pm.EvalProject(i.project_name)
            commit = project.git_repo.commit(i.v2_hash)
            if commit.committed_datetime > datetime.now(UTC) - timedelta(days=3):
                filtered_renames.append(i)
        return filtered_renames


    def run_agent(self, new_renames: List[bm_load.BenchmarkItem]):
        for i in new_renames:
            if i.v2_hash not in self.previously_analysed:

                try:
                    # TODO: Run the agent, minus the IDE parts here
                    agent = self._run_agent(i)
                except:
                    print("Failed to run agent")
                    continue
                self.previously_analysed.append(i.v2_hash)
                self.agent_output.append(
                    {
                        "ref_id": i.ref_id,
                        "augmented_intent": agent.augmented_intent,
                        "recommendations": agent.files_and_planning
                    }
                )
                if len(agent.files_and_planning) > 0:
                    self.send_slack_notification(agent, i)

            with open(self.cache_path, 'w') as f:
                json.dump(self.previously_analysed, f, indent=4)

            with open(self.agent_output_path, 'w') as f:
                json.dump(self.agent_output, f, indent=4)

    def _run_agent(self, bench_item: bm_load.BenchmarkItem):

        project = pm.EvalProject(bench_item.project_name)
        v2_hash = bench_item.v2_hash
        project.checkout(v2_hash, force=True)

        vendor = 'openai'

        improved_commit_message = bench_item.improved_commit_message
        starting_file = bench_item.starting_file

        old_name = improved_commit_message.split(" -> ")[0].split(" ")[-1]
        new_name = improved_commit_message.split(" -> ")[1].split(" ")[0]
        model = ChatOpenAI(model="o4-mini",
                           temperature=1)

        augmented_intent = analysis.AnalysisComponent(
            model=model,
            source_file_path=starting_file,
            source_code=project.get_file_contents(starting_file),
            initial_intent=improved_commit_message,
            old_name=old_name,
            new_name=new_name
        ).run().augmented_intent

        agent = patch_curation_agent.PatchAgent(
            ide_server=ij.IntellijServer.create_default(),
            model_name=f'{vendor}:gpt-4o-mini',
            reasoning_model_name=f'{vendor}:o4-mini',
            project=project,
            plan_component=planning.PlanningComponent,
            augmented_intent=augmented_intent,
            do_replication=True
        )
        agent.add_internal_commit(project.git_repo.commit(v2_hash))
        agent.initialize_agent(starting_file=starting_file)
        agent.perform_replication(augmented_intent, agent.create_model(f'{vendor}:gpt-4o-mini'),
                                  agent.generate_initial_plan(augmented_intent))
        print(agent.augmented_intent)
        print(agent.files_and_planning)
        return agent

    def send_slack_notification(self, agent, bench_item: bm_load.BenchmarkItem):
        project = pm.EvalProject(bench_item.project_name)
        message_content = f"Found a possible patch for {bench_item.ref_id}. See details in the thread."
        commit_time = project.git_repo.commit(bench_item.v2_hash).committed_datetime
        count = len(bench_item.refactoring_changes)
        message_content += f"Ref id: {bench_item.ref_id} \n" \
                           f"Project: {bench_item.project_name} \n" \
                           f"Commit: {project.get_remote_url()}/commit/{bench_item.v2_hash[:7]} \n" \
                           f"Commit date: {commit_time} \n" \
                           f"Number of renames: {count} \n"

        patch_details = f"Augmented intent: {agent.augmented_intent}. \n"
        for file, plan in agent.files_and_planning:
            patch_details += f"File: {file} \n"
            patch_details += f"Possible refactorings: \n ```{plan}``` \n\n"

        client = WebClient(token=os.getenv("SLACK_BOT_TOKEN"))
        response = client.chat_postMessage(channel=os.getenv('SLACK_CHANNEL_ID'),
                                           text=f"Found a possible patch! \n\n {message_content}")
        thread_ts = response.data['ts']
        client.chat_postMessage(channel=os.getenv('SLACK_CHANNEL_ID'), text=f"Details: \n\n {patch_details}",
                                thread_ts=thread_ts)

if __name__ == '__main__':
    PatchCurator(data_file_path=sys.argv[1],
                 should_run_agent=sys.argv[2]=='true').main()