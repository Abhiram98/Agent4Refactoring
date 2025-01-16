import pathlib
import git

projects_base_path = pathlib.Path("/Users/abhiram/Documents/TBE/evaluation_projects")


class EvalProject:
    def __init__(self, project_name):
        self.project_name = project_name
        self.git_repo = git.Repo(self.get_project_path())

    def get_project_path(self):
        project_path = projects_base_path.joinpath(self.project_name)
        return project_path

    def checkout(self, sha1):
        self.git_repo.git.checkout(sha1)

    def checkout_previous(self, sha1):
        self.git_repo.git.checkout(
            self.git_repo.commit(sha1).parents[0])

    def get_file_contents(self, rel_file_path):
        with open(self.get_project_path().joinpath(rel_file_path)) as f:
            return f.read()

    def previous_sha(self, sha1):
        return self.git_repo.commit(sha1).parents[0]
