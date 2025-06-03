import json
import refagent
import pandas as pd
import subprocess


def find_num_commits(project_name):
    result = subprocess.run(
        ['gh', 'api', '-H', 'Accept: application/vnd.github+json',
         '-H', "X-GitHub-Api-Version: 2022-11-28",
         f'/repos/{project_name}/stats/commit_activity'],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )

    response = json.loads(result.stdout.decode('utf-8'))
    return sum([i['total'] for i in response])

if __name__ == '__main__':
    df = pd.read_csv(refagent.data_folder.joinpath('monitoring/projects.csv'))
          # .head(10))
    df['commits_2025'] = df['name'].apply(find_num_commits)
    print(df['commits_2025'])
    df.sort_values(by='commits_2025', ascending=False, inplace=True)
    df.to_csv(refagent.data_folder.joinpath('monitoring/projects_sorted.csv'), index=False)