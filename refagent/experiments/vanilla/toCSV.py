import json
import csv
import argparse


def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Convert JSON refactoring results to CSV format with precision, recall, and F1 statistics",
        add_help=True,
    )
    parser.add_argument(
        "--input-file",
        type=str,
        default="refactoring_results.json",
        help="Input JSON file to process (default: refactoring_results.json)",
    )

    args = parser.parse_args()

    # Determine file names
    input_file = args.input_file
    output_file = input_file[:-5] + ".csv"

    try:
        with open(input_file, "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: Input file '{input_file}' not found.")
        return
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON format in '{input_file}'.")
        return

    precision_sum = 0
    recall_sum = 0
    oracle_count_sum = 0
    f1_sum = 0

    results = []

    for d in data:
        id = d["id"]
        precision = d["precision"]
        recall = d["recall"]
        oracle_count = len(d["refactoring_changes"])
        llm_refactoring_count = len(d["detected_refactorings"])

        # Calculate F1 score
        if precision + recall > 0:
            f1_score = 2 * (precision * recall) / (precision + recall)
        else:
            f1_score = 0

        f1_sum += f1_score
        # Add to results list
        results.append(
            {
                "id": id,
                "precision": precision,
                "recall": recall,
                "f1_score": f1_score,
                "llm_refactoring_count": llm_refactoring_count,
                "oracle_count": oracle_count,
            }
        )

        # Add to sums for averages
        precision_sum += precision
        recall_sum += recall
        oracle_count_sum += oracle_count

    # Calculate averages
    avg_precision = precision_sum / len(data)
    avg_recall = recall_sum / len(data)
    avg_f1 = f1_sum / len(data)

    # Save results to CSV
    try:
        with open(output_file, "w", newline="") as csvfile:
            fieldnames = [
                "id",
                "precision",
                "recall",
                "f1_score",
                "llm_refactoring_count",
                "oracle_count",
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            writer.writeheader()
            for result in results:
                writer.writerow(result)

        print(f"Results saved to: {output_file}")
    except Exception as e:
        print(f"Error writing to CSV file: {e}")
        return

    print(f"average precision: {avg_precision:.4f}")
    print(f"average recall: {avg_recall:.4f}")
    print(f"average f1 score: {avg_f1:.4f}")


if __name__ == "__main__":
    main()
