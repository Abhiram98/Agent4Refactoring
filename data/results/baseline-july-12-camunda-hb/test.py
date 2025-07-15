import json

if __name__ == "__main__":
    with open("/Users/moul7361/Desktop/AI-Agents/Agent4Refactoring/data/ref_miner/rename/camunda_seed.json", "r") as f:
        seed = json.load(f)

    with open("/Users/moul7361/Desktop/AI-Agents/Agent4Refactoring/data/results/baseline-july-12-camunda-ws/planning.json", "r") as f:
        planning = json.load(f)

    processed = set()
    results = []
    for s in seed:
        for p in planning:
            if p["id"] == s["id"] and p['id'] not in processed:
                p['response']['augmented_intent'] = s['change_summary']
                processed.add(p['id'])
                results.append(p)

    with open("/Users/moul7361/Desktop/AI-Agents/Agent4Refactoring/data/results/baseline-july-12-camunda-hb/planning.json", "w") as f:
        json.dump(results, f)