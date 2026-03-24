import json
from json import JSONDecodeError

import refagent
import os
import numpy as np

def compute_avg_runtime(data):
    runtime = [i['elapsedTime']/1000 for i in data]
    return np.mean(runtime)

def compute_avg_review_time(data):
    review = [i['reviewTime']/1000 for i in data]
    return np.mean(review)

def stopped_early_count(data):
    stopped = [i for i in data if i['stoppedEarly']==True]
    return len(stopped)


def stopped_early_time(data):
    stopped = [i for i in data if i['stoppedEarly']==True]
    runtime = [i['elapsedTime']/1000 for i in stopped]
    return np.mean(runtime)

def stopped_review_time(data):
    stopped = [i for i in data if i['stoppedEarly']==True]
    review = [i['reviewTime']/1000 for i in stopped]
    return np.mean(review)

def accepted_count_avg(data):
    counts = [i['acceptedCount'] for i in data]
    return np.mean(counts)

def accepted_count_total(data):
    counts = [i['acceptedCount'] for i in data]
    return sum(counts)

def rejected_count_avg(data):
    counts = [i['rejectedCount'] for i in data]
    return np.mean(counts)

def rejected_count_total(data):
    counts = [i['rejectedCount'] for i in data]
    return sum(counts)

def scope_change_count(data):
    counts = [i['patternChangedCount']+i["guardChangedCount"] for i in data]
    return sum(counts)

def identifiers_inspected_avg(data):
    counts = [i['identifiersInspected'] for i in data]
    return np.mean(counts)

def files_count_avg(data):
    counts = [i['totalFiles'] for i in data]
    return np.mean(counts)

if __name__ == "__main__":
    telemetry_folder = refagent.data_folder.joinpath("telemetry")
    files = [i for i in os.listdir(telemetry_folder) if 'jsonl' in i]

    print(f"{len(files)} telemetry files found in {telemetry_folder}")
    all_data = []

    for fname in files:
        with open(os.path.join(telemetry_folder, fname), "r") as f:
            json_lines = f.readlines()
        for line in json_lines:
            try:
                all_data.append(json.loads(line))
            except JSONDecodeError:
                print("Failed to decode line", line)

    filtered_data = [i for i in all_data if i is not None and i['identifiersInspected'] > 0]
    print("Total invocations: ", len(filtered_data))
    print("Found {} identifiers in telemetry".format(len(filtered_data)))
    print(f"avg runtime = {compute_avg_runtime(filtered_data)/60}")
    print(f"avg review time = {compute_avg_review_time(filtered_data)/60}")
    print(f"stopped early count = {stopped_early_count(filtered_data)}")
    print(f"stopped early time = {stopped_early_time(filtered_data)/60}")
    print(f"stopped review time = {stopped_review_time(filtered_data)/60}")

    print(f"accepted count avg = {accepted_count_avg(filtered_data)}")
    print(f"accepted count total = {accepted_count_total(filtered_data)}")
    print(f"rejected count avg = {rejected_count_avg(filtered_data)}")
    print(f"rejected count total = {rejected_count_total(filtered_data)}")

    print(f"scope change count = {scope_change_count(filtered_data)}")

    print(f"identifiers inspected avg = {identifiers_inspected_avg(filtered_data)}")
    print(f"files count avg = {files_count_avg(filtered_data)}")

