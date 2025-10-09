import json

if __name__ == '__main__':
    with open("data.txt", "r") as file:
        numbers = [int(line.strip()) for line in file if line.strip()]

    # print(numbers)
    print(f"Total numbers: {len(numbers)}")

    with open("intellij-community.json", "r") as file:
        data = json.load(file)

    res = []
    for item in data:
        if item['id']  in numbers:
            res.append(item['id'])

    # print(res)
    # print(f"Total numbers: {len(res)}")

    for i in res:
        print(i, end=",")