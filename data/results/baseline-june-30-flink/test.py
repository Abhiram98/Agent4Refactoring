def main():
    with open('data.txt', 'r') as f:
        lines = f.readlines()

    total = 0
    unique = set()
    for line in lines:
        total += 1
        unique.add(line.strip())

    print(total)
    print(len(unique))
    for x in unique:
        print(x)


if __name__ == '__main__':
    main()