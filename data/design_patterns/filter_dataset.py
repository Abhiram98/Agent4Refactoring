import json
import csv
import os

def update_datasets_with_ids():
    data_dir = os.path.dirname(os.path.abspath(__file__))
    dataset_path = os.path.join(data_dir, 'dpdf_dataset.json')
    metadata_path = os.path.join(data_dir, 'project_metadata.csv')
    output_path = os.path.join(data_dir, 'filtered_dpdf_dataset.json')

    patterns_of_interest = {
        'AbstractFactory', 'Adapter', 'Builder', 'Decorator',
        'Facade', 'FactoryMethod', 'Memento', 'Observer',
        'Prototype', 'Proxy', 'Singleton', 'Visitor'
    }

    # 1. Load star counts and URLs
    star_counts = {}
    project_urls = {}
    with open(metadata_path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            project_name = row['Project Name']
            star_counts[project_name] = int(row['Stars'])
            project_urls[project_name] = row['URL']

    # 2. Assign unique IDs to the main dataset
    with open(dataset_path, mode='r', encoding='utf-8') as f:
        dataset = json.load(f)

    for i, item in enumerate(dataset):
        item['id'] = i + 1  # 1-based unique ID

    # Overwrite main dataset with IDs
    with open(dataset_path, mode='w', encoding='utf-8') as f:
        json.dump(dataset, f, indent=4)
    print(f"Updated {dataset_path} with unique IDs.")

    # 3. Filter and pick top 2
    filtered_instances = []
    for item in dataset:
        pattern = item.get('pattern')
        if pattern in patterns_of_interest:
            project_name = item.get('project_name')
            item['stars'] = star_counts.get(project_name, 0)
            item['github_url'] = project_urls.get(project_name, item.get('github_url'))
            filtered_instances.append(item)

    grouped_by_pattern = {}
    for item in filtered_instances:
        pattern = item['pattern']
        if pattern not in grouped_by_pattern:
            grouped_by_pattern[pattern] = []
        grouped_by_pattern[pattern].append(item)

    final_selection = []
    for pattern in sorted(patterns_of_interest):
        pattern_instances = grouped_by_pattern.get(pattern, [])
        # Sort by stars descending, then by id for stability
        pattern_instances.sort(key=lambda x: (x['stars'], -x['id']), reverse=True)
        
        top_2 = pattern_instances[:2]
        final_selection.extend(top_2)

    # Cleanup temporary 'stars' field and save
    for item in final_selection:
        if 'stars' in item:
            del item['stars']

    with open(output_path, mode='w', encoding='utf-8') as f:
        json.dump(final_selection, f, indent=4)

    print(f"Updated {output_path} with consistent IDs and GitHub URLs.")

if __name__ == '__main__':
    update_datasets_with_ids()
