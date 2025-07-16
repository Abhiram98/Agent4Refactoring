import json

if __name__ == "__main__":
    with open("/Users/raihan/Desktop/AI-Agent/Agent4Refactoring/data/ref_miner/rename/bytechef_seed.json", "r") as f:
        seed = json.load(f)

    with open("/Users/raihan/Desktop/AI-Agent/Agent4Refactoring/data/results/baseline-july-13-bytechef-ws/planning.json", "r") as f:
        planning = json.load(f)

    processed = set()
    results = []
    for s in seed:
        for p in planning:
            if p["id"] == s["id"] and p['id'] not in processed:
                p['response']['augmented_intent'] = s['change_summary']
                processed.add(p['id'])
                results.append(p)

    with open("/Users/raihan/Desktop/AI-Agent/Agent4Refactoring/data/results/baseline-july-13-bytechef-hb/planning.json", "w") as f:
        json.dump(results, f)