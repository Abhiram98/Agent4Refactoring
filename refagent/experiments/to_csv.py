import json
import csv
import os
import refagent
import sys


if __name__ == "__main__":
    input_file = str(
        refagent.repo_root.joinpath(
            f"data/results/{sys.argv[1]}/report-post-replication.json"
        )
    )
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
        "first_file_precision",
        "first_file_recall",
        "tp_starting_file",
        "tp_sec_files",
        "fp_starting_file",
        "fp_sec_files",
        "count_acc_starting_file",
        "count_acc_secondary_files",
        "count_rej_starting_file",
        "count_rej_secondary_files",
        "tp_count",
        "oracle_count",
        "fp_count",
        "human_rejected_count",
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
            print(
                len(entry.get("true_positives")),
                entry.get("tp_starting_file", 0) + entry.get("tp_sec_files", 0),
            )
            # if entry.get("false_positives", 0) or entry.get("false_negatives", 0):
            # entry["tp_starting_file"] =
            # assert len(entry.get("true_positives")) ==  entry.get("tp_starting_file", 0)+ entry.get("tp_sec_files", 0)
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
                "tp_count": len(entry.get("true_positives", [])),
                "fp_count": len(entry.get("false_positives", [])),
                "oracle_count": entry.get("oracle_count", 0),
                "human_review_count": entry.get("human_review_count", 0),
                "human_rejected_count": entry.get("human_rejected_count", 0),
                "first_file_precision": entry.get("first_file_precision", 0),
                "first_file_recall": entry.get("first_file_recall", 0),
                "tp_starting_file": entry.get("tp_starting_file", 0),
                "tp_sec_files": entry.get("tp_sec_files", 0),
                "fp_starting_file": entry.get("fp_starting_file", 0),
                "fp_sec_files": entry.get("fp_sec_files", 0),
                "count_acc_starting_file": entry.get("count_acc_starting_file", 0),
                "count_acc_secondary_files": entry.get("count_acc_secondary_files", 0),
                "count_rej_starting_file": entry.get("count_rej_starting_file", 0),
                "count_rej_secondary_files": entry.get("count_rej_secondary_files", 0),
                # "human_accepted_count": entry.get("human_accepted_count", 0),
                # "human_rejected_count": entry.get("human_rejected_count", 0),
                # "human_accepted_rate": fmt(entry.get("human_accepted_rate", 0)),
            }

            writer.writerow(row)

    print(f"CSV file saved as {output_file}")
