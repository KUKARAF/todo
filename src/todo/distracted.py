"""Standalone CLI to increment a 'distracted' counter in today's diary file frontmatter."""

import re
from datetime import datetime
from today import DiaryDate


def increment_distracted(path):
    """Increment the distracted counter in the YAML frontmatter of the given file."""
    text = path.read_text(encoding="utf-8") if path.exists() else ""

    if text.startswith("---\n"):
        end = text.index("\n---\n", 4)
        front = text[4 : end]
        rest = text[end + 5 :]

        m = re.search(r"^(distracted:\s*)(\d+)", front, re.MULTILINE)
        if m:
            count = int(m.group(2)) + 1
            front = front[: m.start(2)] + str(count) + front[m.end(2) :]
        else:
            count = 1
            front = front.rstrip("\n") + f"\ndistracted: {count}\n"

        path.write_text(f"---\n{front}\n---\n{rest}", encoding="utf-8")
    else:
        count = 1
        path.write_text(f"---\ndistracted: {count}\n---\n{text}", encoding="utf-8")

    return count


def main():
    diary = DiaryDate()
    path = diary.filepath(datetime.now(), create=True)
    count = increment_distracted(path)
    print(f"distracted: {count} ({path.name})")
