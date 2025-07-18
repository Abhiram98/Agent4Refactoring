import json

if __name__ == '__main__':
    with open("no-replication.json") as f:
        data = json.load(f)

    ids = [103392, 112927, 112928, 112929, 113011, 113012, 114311, 114941, 115671, 115691, 115693, 116371, 116372, 116392]

    results = []
    for d in data:
        if d['id'] in ids:
            results.append(d)

    with open('failed-no-replication.json', 'w') as f:
        json.dump(results, f)