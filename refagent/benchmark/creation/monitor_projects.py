import json
import os
import refagent
import refagent.utils.project_manager as pm
import argparse
from pydantic import BaseModel, PrivateAttr
from typing import List, Set
import refagent.benchmark.load as bm_load
import refagent.benchmark.creation.scrape_project as scrape
from datetime import datetime, UTC, timedelta, timezone
from pathlib import Path
import traceback
from slack_sdk import WebClient


class Monitor(BaseModel):
    output_file_path: Path = refagent.data_folder.joinpath("monitoring").joinpath(
        "monitor_results.jsonl"
    )
    cutoff_date: datetime
    _output_json: List = PrivateAttr(default=[])
    _previously_analysed_commits: Set[str] = PrivateAttr(default=[])
    _used_ids: Set[int] = PrivateAttr(default=[])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initialize_directory()

        with open(
            refagent.data_folder.joinpath("monitoring").joinpath(
                "previously_analysed_commits.json"
            )
        ) as f:
            commits = json.load(f)
        self._previously_analysed_commits = set(commits)

        with open(
            refagent.data_folder.joinpath("monitoring").joinpath("used_ids.json")
        ) as f:
            self._used_ids = set(json.load(f))

    def initialize_directory(self):
        if not refagent.data_folder.joinpath("monitoring").exists():
            refagent.data_folder.joinpath("monitoring").mkdir()
        if (
            not refagent.data_folder.joinpath("monitoring")
            .joinpath("previously_analysed_commits.json")
            .exists()
        ):
            with open(
                refagent.data_folder.joinpath("monitoring").joinpath(
                    "previously_analysed_commits.json"
                ),
                "w",
            ) as f:
                json.dump([], f, indent=4)
        if (
            not refagent.data_folder.joinpath("monitoring")
            .joinpath("used_ids.json")
            .exists()
        ):
            with open(
                refagent.data_folder.joinpath("monitoring").joinpath("used_ids.json"),
                "w",
            ) as f:
                json.dump([], f, indent=4)

    def process_project(self, project: pm.EvalProject) -> List[bm_load.BenchmarkItem]:
        monitoring_data = []
        print("pulling repo")
        project.checkout_main()
        project.pull_project()
        print("done pulling repo")

        for commit in project.git_repo.iter_commits(project.git_repo.head):
            if commit.hexsha in self._previously_analysed_commits:
                print(f"commit {commit.hexsha} was previously analysed. skipping")
                continue

            if commit.committed_datetime < self.cutoff_date:
                print(f"commit {commit.hexsha} is older than cutoff date. skipping")
                print("Stopping loop.")
                break

            data = scrape.RenameProcessor(
                id_counter=self.get_new_id(),
                project=project,
                commit=commit,
            ).process_commit()
            if data is not None:
                monitoring_data.append(data)
                self.append_result(data)
                self.send_slack_messages([data])
                self._used_ids.add(data.ref_id)
            else:
                print(f"commit {commit.hexsha} was not added to the monitoring data")

            self._previously_analysed_commits.add(commit.hexsha)
            self.save_monitored_commit()
            print(f"commit {commit.hexsha} was added to the monitoring data")
            self.save_used_ids()

        return monitoring_data

    def save_monitored_commit(self):
        with open(
            refagent.data_folder.joinpath("monitoring").joinpath(
                "previously_analysed_commits.json"
            ),
            "w",
        ) as f:
            json.dump(list(self._previously_analysed_commits), f, indent=4)

    def append_result(self, data: bm_load.BenchmarkItem):
        with open(self.output_file_path, "a") as f:
            f.write(json.dumps(data.to_json()) + "\n")

    def run(self, project_names: List[str]):
        new_data = []
        for name in project_names:
            print("Analyzing project: ", name, " ...")
            project = pm.EvalProject(name)
            try:
                new_data += self.process_project(project)
            except:
                print(f"failed to process project {name}")
                traceback.print_exc()
        # try:
        #     self.send_slack_messages(new_data)
        # except:
        #     print("failed to send slack message")
        #     traceback.print_exc()

    def send_slack_messages(self, new_data: List[bm_load.BenchmarkItem]):
        try:
            message_content = ""
            for data in new_data:
                renames_str = ""
                count = 0
                for ref in data.refactoring_changes:
                    if ref.type.startswith("Rename"):
                        renames_str += (
                            f"{ref.type}: {ref.old_name} -> {ref.new_name} \n"
                        )
                        count += 1
                project_obj = pm.EvalProject(data.project_name)

                commit_time = str(
                    project_obj.git_repo.commit(data.v2_hash).authored_datetime
                )

                # send message only if the commit is in the last two days
                should_send_message = project_obj.git_repo.commit(
                    data.v2_hash
                ).committed_datetime > datetime.now(UTC) - timedelta(days=2)
                if not should_send_message:
                    continue
                message_content += (
                    f"Ref id: {data.ref_id} \n"
                    f"Project: {data.project_name} \n"
                    f"Commit: {project_obj.get_remote_url()}/commit/{data.v2_hash[:7]} \n"
                    f"Commit date: {commit_time} \n"
                    f"Number of renames: {count} \n"
                )
                client = WebClient(token=os.getenv("SLACK_BOT_TOKEN"))
                response = client.chat_postMessage(
                    channel=os.getenv("SLACK_CHANNEL_ID"),
                    text=f"Found new renames! \n\n {message_content}",
                )
                thread_ts = response.data["ts"]
                client.chat_postMessage(
                    channel=os.getenv("SLACK_CHANNEL_ID"),
                    text=f"Renames: \n\n {renames_str}",
                    thread_ts=thread_ts,
                )
        except:
            print("failed to send slack message")
            traceback.print_exc()

    def get_new_id(self):
        return max(self._used_ids) if len(self._used_ids) > 0 else 10000

    def save_used_ids(self):
        with open(
            refagent.data_folder.joinpath("monitoring").joinpath("used_ids.json"), "w"
        ) as f:
            json.dump(list(self._used_ids), f, indent=4)


def main():
    parser = argparse.ArgumentParser(description="monitor different projects")
    parser.add_argument(
        "project_names_file", type=str, help="File containing project names to monitor"
    )
    parser.add_argument(
        "--cutoff_date",
        type=str,
        default=(datetime.now(timezone.utc) - timedelta(days=2)).date().isoformat(),
        help="Cutoff date for commits to monitor from",
    )
    args = parser.parse_args()

    with open(args.project_names_file) as f:
        project_names = [i for i in f.read().split("\n") if i != ""]
    Monitor(
        cutoff_date=datetime.fromisoformat(args.cutoff_date).replace(tzinfo=UTC),
    ).run(project_names)


if __name__ == "__main__":
    main()
