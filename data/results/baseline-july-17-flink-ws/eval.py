import json
import csv

if __name__ == '__main__':
    file_name = "report-post-replication"
    with open(f"{file_name}.json", "r") as f:
        data = json.load(f)

    precision_sum = 0
    recall_sum = 0
    oracle_count_sum = 0
    f1_sum = 0

    # List to store all entries with calculated F1 scores
    results = []

    for d in data:
        id = d['id']
        precision = d['precision']
        recall = d['recall']
        oracle_count = d['oracle_count']
        agent_refactoring_count = d['agent_refactoring_count']
        true_positives_count = len(d['true_positives'])

        # Calculate F1 score
        if precision + recall > 0:
            f1_score = 2 * (precision * recall) / (precision + recall)
        else:
            f1_score = 0

        f1_sum += f1_score
        # Add to results list
        results.append({
            'id': id,
            'precision': precision,
            'recall': recall,
            'f1_score': f1_score,
            'agent_refactoring_count': agent_refactoring_count,
            'oracle_count': oracle_count,
            'true_positives_count': true_positives_count,
        })

        # Add to sums for averages
        precision_sum += precision
        recall_sum += recall
        oracle_count_sum += oracle_count

    # Calculate averages
    avg_precision = precision_sum / len(data)
    avg_recall = recall_sum / len(data)
    avg_f1 = f1_sum / len(data)

    # Save results to CSV
    with open(f"{file_name}.csv", "w", newline='') as csvfile:
        fieldnames = ['id', 'precision', 'recall', 'f1_score', 'agent_refactoring_count', 'oracle_count', 'true_positives_count']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        for result in results:
            writer.writerow(result)

    print(f"average precision: {avg_precision:.4f}")
    print(f"average recall: {avg_recall:.4f}")
    print(f"average f1 score: {avg_f1:.4f}")
    print(f"Results saved to eval_results.csv")