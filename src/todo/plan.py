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


def cmd_plan(files: list[str]) -> None:
    """Move open tasks and copy partial tasks into today's file, then open editor."""
    diary = DiaryDate()
    today_path = diary.filepath(datetime.now(), create=True)
    today_resolved = str(today_path.resolve())

    tasks_to_add = []
    files_to_rewrite = {}  # file_path -> (original_lines, indices_to_remove)

    for file_path in files:
        path = Path(file_path)
        if not path.exists():
            continue
        if str(path.resolve()) == today_resolved:
            continue

        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        lines_to_remove = []

        for idx, line in enumerate(lines):
            task_type = classify_task(line)
            if task_type == 'open':
                tasks_to_add.append(line.rstrip('\n'))
                lines_to_remove.append(idx)
            elif task_type == 'partial':
                tasks_to_add.append(line.rstrip('\n'))

        if lines_to_remove:
            files_to_rewrite[file_path] = (lines, lines_to_remove)

    if not tasks_to_add:
        print("No tasks to plan for today")
        return

    # Append tasks to today's file
    with open(today_path, 'a', encoding='utf-8') as f:
        for task in tasks_to_add:
            f.write(task + '\n')

    # Remove moved tasks from source files (atomic writes)
    for file_path, (lines, remove_indices) in files_to_rewrite.items():
        remove_set = set(remove_indices)
        new_lines = [line for idx, line in enumerate(lines) if idx not in remove_set]

        path = Path(file_path)
        tmp_path = path.with_suffix(path.suffix + '.tmp')
        with open(tmp_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        tmp_path.replace(path)

    print(f"\U0001f4cb Planned {len(tasks_to_add)} task(s) for today ({today_path.name})")

    # Append suggested plan from estimate_today.prompt (includes calendar events)
    result = subprocess.run(
        ["estimate_today.prompt"],
        capture_output=True, text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        with open(today_path, 'a', encoding='utf-8') as f:
            f.write('\n# suggested plan\n')
            f.write(result.stdout)
    else:
        print("No suggested plan (or estimate_today.prompt failed)")

    # Open today's file in editor
    subprocess.run("today | todo edit", shell=True)
