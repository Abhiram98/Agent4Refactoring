if __name__ == "__main__":
    with open("data.txt", "r") as f:
        ans = set()
        data = f.readlines()
        for entry in data:
            ans.add(entry.strip())

    print(len(ans))
