import json

if __name__ == '__main__':
    with open('flink_seed.json', 'r') as f:
        data = json.load(f)

    ans = 0
    for d in data:
        ans += len(d['refactoring_changes'])

    print(ans)