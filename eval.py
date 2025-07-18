import json
import csv

def main():
    json_file = "refactoring_results_bytechef.json"
    with open(json_file) as f:
        data = json.load(f)

    recall = 0
    precision = 0
    f1_score = 0
    total_dp = len(data)

    # Prepare data for CSV export
    csv_data = []

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

        # Add to CSV data
        csv_data.append({
            'id': item.get('id', ''),  # Use empty string if id doesn't exist
            'recall': item_recall,
            'precision': item_precision,
            'f1_score': item_f1
        })

    # Save to CSV
    csv_file = "refactoring_results_bytechef.csv"
    with open(csv_file, 'w', newline='') as csvfile:
        fieldnames = ['id', 'recall', 'precision', 'f1_score']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        for row in csv_data:
            writer.writerow(row)

    print(f"Data saved to {csv_file}")
    print(f"Average Recall: {recall / total_dp}")
    print(f"Average Precision: {precision / total_dp}")
    print(f"Average F1-Score: {f1_score / total_dp}")


if __name__ == "__main__":
    main()