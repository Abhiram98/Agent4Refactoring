from github import Github, Auth, Repository
from git import Commit

# Authentication is defined via github.Auth
from pydantic import BaseModel, Field, computed_field
import subprocess
import json
from datetime import datetime
from typing import Optional

import refagent.utils.project_manager as pm
import refagent


class PrComment(BaseModel):
    comment: str = Field(description="the comment.")
    time: datetime = Field(description="the timestamp when the comment was made.")
    author: str = Field(description="the name of the commenter.")


class PrReviewComment(PrComment):
    file_path: str = Field(description="file which was commented upon")
    start_line_num: int = Field(description="start line where the comment was made.")
    # end_line_num: Optional[int] = Field(description="end line where the comment was made.")
    diff_hunk: str = Field(description="diff hunk where the comment was made.")
    comment_url: str = Field(description="url to locate the comment")
    commit_id: str = Field(
        description="commit id?"
    )  # TODO: not sure what this exactly holds.
    original_commit_id: str = Field(
        description="original commit id?"
    )  # TODO: Not sure what this exactly holds


class GithubPR(BaseModel):
    title: str = Field(description="title of the PR")
    body: str = Field(description="body of the PR")
    comments: list[PrComment] = Field(
        description="list of comments made during "
        "the review process, as seen on the pr directly."
    )
    number: int = Field(description="Pull request number")
    updated_at: datetime = Field(description="last updated time of the PR")
    created_at: datetime = Field(description="time of PR creation")
    review_comments: list[PrReviewComment] = Field(
        description="Fine grained comments left by"
        " reviewers about changing particular lines of code."
    )


class CommentImporter(BaseModel):
    project: pm.EvalProject = Field(description="project to work upon")

    model_config = {"arbitrary_types_allowed": True}

    @computed_field()
    def repo_name(self) -> str:
        remote_url = self.project.git_repo.remotes[1].url
        repo_name = remote_url.split(".git")[0].split("github.com/")[-1]
        return repo_name

    @computed_field()
    def github_repo(self) -> Repository:
        g = Github()
        return g.get_repo(self.repo_name)

    def get_comments(self, v1_sha, v2_sha: str) -> GithubPR:
        """
        Find the comments associated with the PR in which the sha was involved in
        :param sha: hash to look for
        """
        # v1_commit_time = self.project.git_repo.commit(v1_sha).authored_datetime
        v2_commit_time = self.project.git_repo.commit(v2_sha).authored_datetime
        # assert v2_commit_time > v1_commit_time

        pr_num = self.get_pr_num(
            self.project.git_repo.commit(v2_sha),
            self.project.git_repo.commit(v1_sha).committed_datetime,
        )

        print(f"{pr_num=}")
        pr_obj = self.get_pr_comments(pr_num, v2_commit_time)
        return pr_obj

        # Filter comments in between v1_sha and v2_sha.

    def get_pr_num(self, sha: Commit, v1_commit_time) -> int:
        result = subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--repo",
                self.repo_name,
                "--search",
                str(sha.hexsha)[:8],
                "--state",
                "all",
                "--json",
                "number,createdAt",
            ],
            stdout=subprocess.PIPE,
        )
        pr_json = result.stdout.decode("utf-8")
        pr_data = json.loads(pr_json)
        if len(pr_data) == 0:
            # Retry seach with commit message
            first_message = sha.message.split("\n")[0]
            result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "list",
                    "--repo",
                    self.repo_name,
                    "--search",
                    first_message,
                    "--state",
                    "all",
                    "--json",
                    "number,createdAt",
                ],
                stdout=subprocess.PIPE,
            )
            pr_json = result.stdout.decode("utf-8")
            pr_data = json.loads(pr_json)
        filtered_prs = [
            i
            for i in pr_data
            if datetime.fromisoformat(i["createdAt"]) < v1_commit_time
        ]
        assert len(filtered_prs) == 1
        return filtered_prs[0]["number"]

    def get_pr_comments(self, pr_num, v2_commit_time) -> GithubPR:
        result = subprocess.run(
            [
                "gh",
                "pr",
                "view",
                f"{pr_num}",
                "--repo",
                f"{self.repo_name}",
                "--comments",
                "--json",
                "title,body,updatedAt,createdAt,comments,reviews",
            ],
            stdout=subprocess.PIPE,
        )
        pr_comments_json = json.loads(result.stdout.decode("utf-8"))
        comments_objs = [
            PrComment(
                author=i["author"]["login"],
                comment=i["body"],
                time=datetime.fromisoformat(i["createdAt"]),
            )
            for i in pr_comments_json["comments"]
        ]
        comments_objs += [
            PrComment(
                author=i["author"]["login"],
                comment=i["body"],
                time=datetime.fromisoformat(i["submittedAt"]),
            )
            for i in pr_comments_json["reviews"]
        ]
        filtered_comments = [i for i in comments_objs if i.time < v2_commit_time]
        # filtered_comments = comments_objs

        review_comments = self.get_review_comments(pr_num, v2_commit_time)

        return GithubPR(
            title=pr_comments_json["title"],
            body=pr_comments_json["body"],
            created_at=datetime.fromisoformat(pr_comments_json["createdAt"]),
            updated_at=datetime.fromisoformat(pr_comments_json["updatedAt"]),
            comments=filtered_comments,
            review_comments=review_comments,
            number=pr_num,
        )

    def get_review_comments(
        self, pr_num: int, v2_commit_time: datetime
    ) -> list[PrReviewComment]:
        """Retrieve the fine-grained comments made on each line number of the review."""
        # "gh api -X GET /repos/apache/flink/pulls/23752/comments "
        result = subprocess.run(
            [
                "gh",
                "api",
                "-X",
                "GET",
                f"/repos/{self.repo_name}/pulls/{pr_num}/comments",
            ],
            stdout=subprocess.PIPE,
        )
        review_comments_json = json.loads(result.stdout.decode("utf-8"))
        review_comments = [
            PrReviewComment(
                comment=i["body"],
                time=datetime.fromisoformat(i["created_at"]),
                author=i["user"]["login"],
                file_path=i["path"],
                commit_id=i["commit_id"],
                original_commit_id=i["original_commit_id"],
                start_line_num=i["original_line"],
                diff_hunk=i["diff_hunk"],
                comment_url=i["html_url"],
            )
            for i in review_comments_json
        ]
        return [i for i in review_comments if i.time < v2_commit_time]
        # return review_comments


if __name__ == "__main__":
    import os

    json_files = [
        i
        for i in os.listdir(refagent.data_folder.joinpath("ref_miner"))
        if i.endswith(".json")
    ]

    for filename in json_files:
        print(f"processing {filename}")
        with open(refagent.data_folder.joinpath(f"ref_miner/{filename}")) as f:
            data = json.load(f)

        for i, bench_item in enumerate(data):
            print(f"{i}/{len(data)}")
            if bench_item.get("pull_request"):
                print("Skipping because of previously fetched data")
                continue

            try:
                pr = CommentImporter(
                    project=pm.EvalProject(bench_item["project"])
                ).get_comments(bench_item["v1_hash"], bench_item["v2_hash"])
                bench_item["pull_request"] = pr.model_dump(mode="json")
            except Exception as e:
                print(f"failed to get PR data for {bench_item['id']}")
                print(e)

        with open(refagent.data_folder.joinpath(f"ref_miner/{filename}"), "w") as f:
            json.dump(data, f, indent=4)
