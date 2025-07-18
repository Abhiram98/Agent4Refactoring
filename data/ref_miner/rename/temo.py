import json
RENAME_TYPES = {
    'Rename Class',
    'Rename Method',
    'Rename Variable',
    'Rename Parameter',
    'Rename Attribute',
    'Rename Package'
}

if __name__ == '__main__':
    # with open('flink_test.json', 'r') as f:
    #     data = json.load(f)
    #
    # res = []
    # for item in data:
    #     for r in item['refactoring_changes']:
    #         if r['type'] in RENAME_TYPES:
    #             print(r)
    #             res.append(r)
    #
    #     item['refactoring_changes'] = res
    #
    #
    # with open('flink_test_rename.json', 'w') as f:
    #     json.dump(data, f, indent=4)

    with open('camunda_seed.json', 'r') as f:
        data = json.load(f)

    res = []
    for item in data:
        if item['seed_hash'] is None:
            res.append(item['id'])

    print(res)


