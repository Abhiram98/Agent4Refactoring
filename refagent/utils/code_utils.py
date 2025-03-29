
def add_line_numbers(text):
    lines = text.split('\n')
    numbered_lines = [f"{i + 1}: {line}" for i, line in enumerate(lines)]
    return '\n'.join(numbered_lines)