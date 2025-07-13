import json

if __name__ == "__main__":
    with open('no-replication.json') as f:
        rep = json.load(f)

    with open('/Users/raihan/Desktop/AI-Agent/Agent4Refactoring/data/ref_miner/rename/flink_seed_no_seed.json') as f:
        seed = json.load(f)
    res = []
    id_set_rep = set()
    id_set_seed = set()

    for i in rep:
        id_set_rep.add(i['id'])
    for i in seed:
        id_set_seed.add(i['id'])

    for i in rep:
        if i['id'] not in id_set_seed:
            res.append(i)


    with open('flink_seed_no_seed_no_rep.json', 'w') as f:
        json.dump(res, f, indent=4)
