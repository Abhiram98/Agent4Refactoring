import json


def main():
    json_file = "refactoring_results_ratpack.json"
    with open(json_file) as f:
        data = json.load(f)

    recall = 0
    precision = 0
    f1_score = 0
    total_dp = len(data)
    print("len of datapoints: ", len(data))

    for item in data:
        recall += item['recall']
        precision += item['precision']

        # Calculate F1-score for this item
        item_recall = item['recall']
        item_precision = item['precision']

        # Handle division by zero case
        if item_recall + item_precision == 0:
            item_f1 = 0
        else:
            item_f1 = 2 * (item_precision * item_recall) / (item_precision + item_recall)

        f1_score += item_f1

    print(f"Average Recall: {recall / total_dp}")
    print(f"Average Precision: {precision / total_dp}")
    print(f"Average F1-Score: {f1_score / total_dp}")


if __name__ == "__main__":
    main()