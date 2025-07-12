import json


def main():
    json_file = "refactoring_results_argouml.json"
    with open(json_file) as f:
        data = json.load(f)

    recall = 0
    precision = 0
    total_dp = len(data)
    for item in data:
        recall += item['recall']
        precision += item['precision']

    print(f"Average Recall: {recall/total_dp}")
    print(f"Average Precision: {precision/total_dp}")


if __name__ == "__main__":
    main()