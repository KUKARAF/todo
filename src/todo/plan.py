"""
Plan command: consolidate incomplete tasks into today's file.

Usage:
    today | todo plan       # Plan from today's file(s)
    week | todo plan        # Plan from this week's files
    todo plan               # Default: plan from last 3 days
"""

import sys
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from today import DiaryDate


def get_default_files() -> list[str]:
    """Get diary files for the last 3 days (excluding today)."""
    diary = DiaryDate()
    files = []
    now = datetime.now()
    for days_ago in range(1, 4):
        dt = now - timedelta(days=days_ago)
        path = diary.filepath(dt)
        if path.exists():
            files.append(str(path))
    return files


def classify_task(line: str) -> str | None:
    """
    Classify a markdown task line.
    Returns:
        'open' for - [ ] (unchecked, should be moved)
        'partial' for - [m], - [p], etc. (semi-done, should be copied)
        'done' for - [x] (done, skip)
        None for non-task lines
    """
    match = re.match(r'^\s*[-*]\s+\[(.)\]\s+', line)
    if not match:
        return None
    marker = match.group(1)
    if marker == 'x':
        return 'done'
    elif marker == ' ':
        return 'open'
    else:
        return 'partial'


def has_plan(path: Path) -> bool:
    """Check if plan: true is set in the YAML frontmatter."""
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return False
    try:
        end = text.index("\n---\n", 4)
    except ValueError:
        return False
    front = text[4:end]
    return bool(re.search(r"^plan:\s*true\s*$", front, re.MULTILINE))


def set_frontmatter_plan(path: Path) -> None:
    """Set plan: true in the YAML frontmatter of the given file."""
    text = path.read_text(encoding="utf-8") if path.exists() else ""

    if text.startswith("---\n"):
        end = text.index("\n---\n", 4)
        front = text[4:end]
        rest = text[end + 5:]

        if re.search(r"^plan:", front, re.MULTILINE):
            front = re.sub(r"^plan:.*$", "plan: true", front, flags=re.MULTILINE)
        else:
            front = front.rstrip("\n") + "\nplan: true\n"

        path.write_text(f"---\n{front}\n---\n{rest}", encoding="utf-8")
    else:
        path.write_text(f"---\nplan: true\n---\n{text}", encoding="utf-8")


def _collect_tasks(files: list[str], target_resolved: str) -> tuple[list[str], dict]:
    """Collect open/partial tasks from files, skipping the target file.

    Returns (tasks_to_add, files_to_rewrite).
    files_to_rewrite maps file_path -> (original_lines, indices_to_remove, indices_to_mark_done).
    """
    tasks_to_add = []
    files_to_rewrite = {}

    for file_path in files:
        path = Path(file_path)
        if not path.exists():
            continue
        if str(path.resolve()) == target_resolved:
            continue

        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        lines_to_remove = []
        lines_to_mark_done = []

        for idx, line in enumerate(lines):
            task_type = classify_task(line)
            if task_type == 'open':
                tasks_to_add.append(line.rstrip('\n'))
                lines_to_remove.append(idx)
            elif task_type == 'partial':
                tasks_to_add.append(line.rstrip('\n'))
                lines_to_mark_done.append(idx)

        if lines_to_remove or lines_to_mark_done:
            files_to_rewrite[file_path] = (lines, lines_to_remove, lines_to_mark_done)

    return tasks_to_add, files_to_rewrite


def _write_tasks(target_path: Path, tasks: list[str], files_to_rewrite: dict) -> None:
    """Append tasks to target file, remove open tasks and mark partial tasks done in sources."""
    with open(target_path, 'a', encoding='utf-8') as f:
        for task in tasks:
            f.write(task + '\n')

    for file_path, (lines, remove_indices, mark_done_indices) in files_to_rewrite.items():
        remove_set = set(remove_indices)
        mark_done_set = set(mark_done_indices)
        new_lines = []
        for idx, line in enumerate(lines):
            if idx in remove_set:
                continue
            if idx in mark_done_set:
                new_lines.append(re.sub(r'^(\s*[-*]\s+)\[.\]', r'\1[x]', line))
            else:
                new_lines.append(line)

        path = Path(file_path)
        tmp_path = path.with_suffix(path.suffix + '.tmp')
        with open(tmp_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        tmp_path.replace(path)


def cmd_plan(files: list[str]) -> None:
    """Move open tasks and copy partial tasks into today's (or tomorrow's) file, then open editor."""
    diary = DiaryDate()
    now = datetime.now()
    today_path = diary.filepath(now, create=True)

    # If today already has a plan, target tomorrow instead
    planning_tomorrow = has_plan(today_path)
    if planning_tomorrow:
        target_path = diary.filepath(now + timedelta(days=1), create=True)
        estimate_cmd = "estimate_tomorrow.prompt"
        label = "tomorrow"
        # Include today as a source so unfinished tasks move to tomorrow
        today_str = str(today_path)
        if today_str not in files:
            files = files + [today_str]
    else:
        target_path = today_path
        estimate_cmd = "estimate_today.prompt"
        label = "today"

    target_resolved = str(target_path.resolve())

    tasks_to_add, files_to_rewrite = _collect_tasks(files, target_resolved)

    if tasks_to_add:
        _write_tasks(target_path, tasks_to_add, files_to_rewrite)
        print(f"\U0001f4cb Planned {len(tasks_to_add)} task(s) for {label} ({target_path.name})")
    else:
        print(f"No tasks to move for {label}")

    set_frontmatter_plan(target_path)

    # Append suggested plan from estimate prompt
    result = subprocess.run(
        [estimate_cmd],
        capture_output=True, text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        with open(target_path, 'a', encoding='utf-8') as f:
            f.write('\n# suggested plan\n')
            f.write(result.stdout)
    else:
        print(f"No suggested plan (or {estimate_cmd} failed)")

    # Open target file in editor
    subprocess.run(f"echo {target_path} | todo edit", shell=True)
