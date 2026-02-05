import json
import pandas as pd

if __name__ == '__main__':
    with open('analyzed_repo.json', 'r') as f:
        analyzed_repo = json.load(f)

    df = pd.read_csv('analysis_result/projects_sorted.csv')

    for data in analyzed_repo:
        if data['repo_url'] == "":
            for index, row in df.iterrows():
                if data['project'] in row['name'].split('/')[-1]:
                    data['repo_url'] = f'https://github.com/{row['name']}.git'

    with open('analyzed_repo.json', 'w') as f:
        json.dump(analyzed_repo, f)
