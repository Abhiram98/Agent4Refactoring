import json
import csv
import os

if __name__ == "__main__":
    input_file = "/Users/moul7361/Desktop/AI-Agents/Agent4Refactoring/data/results/camunda-oct-1-smaller-model/report-post-replication.json"
    output_file = os.path.splitext(input_file)[0] + ".csv"

    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Define CSV columns
    fields = [
        "id",
        # "oracle_count",
        # "agent_refactoring_count",
        "recall",
        "precision",
        "f1_score",
        # "len_true_positives",
        "human_review_count",
        # "human_accepted_count",
        # "human_rejected_count",
        # "human_accepted_rate"
    ]

    def fmt(value):
        """Format floats to 4 decimals, leave others unchanged."""
        if isinstance(value, float):
            return round(value, 6)
        return value

    # Write to CSV
    with open(output_file, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fields)
        writer.writeheader()

        for entry in data:
            recall = entry.get("recall", 0) or 0
            # precision = entry.get("precision", 0) or 0
            precision = entry.get("human_accepted_rate", 0)

            # Calculate F1 score
            if (precision + recall) > 0:
                f1_score = 2 * (precision * recall) / (precision + recall)
            else:
                f1_score = 0.0

            row = {
                "id": entry.get("id"),
                # "oracle_count": entry.get("oracle_count", 0),
                # "agent_refactoring_count": entry.get("agent_refactoring_count", 0),
                "recall": fmt(recall),
                # "precision": fmt(precision),
                "precision": fmt(entry.get("human_accepted_rate", 0)),
                "f1_score": fmt(f1_score),
                # "len_true_positives": len(entry.get("true_positives", [])),
                "human_review_count": entry.get("human_review_count", 0),
                # "human_accepted_count": entry.get("human_accepted_count", 0),
                # "human_rejected_count": entry.get("human_rejected_count", 0),
                # "human_accepted_rate": fmt(entry.get("human_accepted_rate", 0)),
            }

            writer.writerow(row)

    print(f"CSV file saved as {output_file}")
