import json
import csv

def main():
    json_file = "compile_errors_results.json"
    with open(json_file) as f:
        data = json.load(f)

    total_error = 0
    no_of = 0

    for item in data:
        if item['compile_errors'] > 0:
            total_error += item['compile_errors']
            no_of += 1


    print(f"Total number of errors: {total_error}")
    print(f"Average: {total_error /no_of }")
    print(f"Total number of: {no_of}")
    print(f"Percentage: {no_of / 72}")




if __name__ == "__main__":
    main()