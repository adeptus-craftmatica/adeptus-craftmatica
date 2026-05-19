import os

# Folders/files to ignore
IGNORE = {
    ".venv",
    "venv",
    "__pycache__",
    ".git",
    ".idea",
    ".mypy_cache",
    ".pytest_cache",
    ".DS_Store",
    "splashscreens",
    "testfiles",
}

def print_tree(start_path=".", prefix=""):
    items = sorted(os.listdir(start_path))

    # Filter ignored items
    items = [item for item in items if item not in IGNORE]

    for index, item in enumerate(items):
        path = os.path.join(start_path, item)
        is_last = index == len(items) - 1

        connector = "└── " if is_last else "├── "
        print(prefix + connector + item)

        if os.path.isdir(path):
            extension = "    " if is_last else "│   "
            print_tree(path, prefix + extension)


if __name__ == "__main__":
    print(os.path.basename(os.getcwd()))
    print_tree()