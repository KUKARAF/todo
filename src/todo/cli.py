"""
CLI tool for managing todos from markdown files.

Usage:
    diary | todo get                          # Show todos due today or overdue
    diary | todo edit                         # Open files in default editor
    diary week | todo show                    # Print all todos from week
    diary | todo done                         # Interactive (fzf) mark done
    todo add "task text #tag @location"       # Add new todo (uses today's file by default)
    todo add "task due:tomorrow #tag"         # Add todo with custom due date
    todo done path/to/file.md 42              # Directly mark line 42 in file as done
    todo postpone                             # Interactive (fzf) move todo to another day
    todo send                                 # Push top-7 todos to HA epaper helpers
"""

import sys
import subprocess
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from todo import Todo
from today import DiaryDate
from todo.plan import cmd_plan, get_default_files
from todo.defaults import default_files
from todo.epaper import EPaper


def read_files_from_stdin() -> list[str]:
    """Read file paths from stdin"""
    files = []
    for line in sys.stdin:
        line = line.strip()
        if line and line.endswith('.md'):
            files.append(line)
    return files


def parse_args() -> tuple[str, list[str]]:
    """Parse command line arguments"""
    if len(sys.argv) < 2:
        print("Usage: <files> | todo <command>", file=sys.stderr)
        print("       todo add <text>", file=sys.stderr)
        print("       todo done [<file_path> <line_number>]", file=sys.stderr)
        print("       todo plan", file=sys.stderr)
        print("       todo postpone", file=sys.stderr)
        print("Commands: get, show, edit, add, done, plan, postpone, send", file=sys.stderr)
        sys.exit(1)

    command = sys.argv[1].lower()

    # 'add', 'done', and 'plan' don't require stdin
    if command in ('add', 'done', 'plan', 'postpone', 'send'):
        if command == 'add' and len(sys.argv) < 3:
            print("Usage: todo add <text>", file=sys.stderr)
            sys.exit(1)
        # done with two extra args = direct mode; otherwise it's interactive and needs stdin
        if command == 'done' and len(sys.argv) >= 4:
            return command, []  # direct mode
        return command, []

    if not sys.stdin.isatty():
        files = read_files_from_stdin()
    else:
        files = []

    if not files:
        files = default_files(command)

    if not files:
        print("Error: No files provided via stdin and no defaults available", file=sys.stderr)
        sys.exit(1)

    return command, files


def print_todo(todo_id: int, item: dict) -> None:
    """Print a single todo item"""
    text = item['text'].strip()
    # Remove checkbox for cleaner display
    text = text.replace('- [ ]', '').replace('* [ ]', '').strip()

    due_date_str = ""
    if item['due_date']:
        due_date_str = f" \U0001f4c5 {item['due_date'].strftime('%Y-%m-%d %H:%M')}"

    tags_str = ""
    if item['tags']:
        tags_str = f" {' '.join(f'#{tag}' for tag in item['tags'])}"

    locations_str = ""
    if item['locations']:
        locations_str = f" {' '.join(f'@{loc}' for loc in item['locations'])}"

    file_str = f"  ({Path(item['file']).name}:{item['line_number']})"

    print(f"{text}{due_date_str}{tags_str}{locations_str}{file_str}")


def cmd_show(files: list[str]) -> None:
    """Show all todos from given files"""
    todo = Todo(files)
    all_todos = todo.get_all()

    if not all_todos:
        print("No todos found")
        return

    # Group by file for organization
    todos_by_file = {}
    for todo_id, item in all_todos.items():
        file_path = item['file']
        if file_path not in todos_by_file:
            todos_by_file[file_path] = []
        todos_by_file[file_path].append((todo_id, item))

    for file_path in sorted(todos_by_file.keys()):
        print(f"\n\U0001f4c4 {Path(file_path).name}")
        print("\u2500" * 60)
        for todo_id, item in todos_by_file[file_path]:
            print_todo(todo_id, item)


def cmd_get(files: list[str]) -> None:
    """Show todos due today/overdue, or Eisenhower quadrant if none due"""
    todo = Todo(files)
    all_todos = todo.get_all()

    if not all_todos:
        print("No todos found")
        return

    today = datetime.now().date()

    # Find todos due today or overdue
    due_today_or_overdue = {}
    for todo_id, item in all_todos.items():
        if item['due_date']:
            due_date = item['due_date'].date()
            if due_date <= today:
                due_today_or_overdue[todo_id] = item

    if due_today_or_overdue:
        print("\U0001f4cc Due Today or Overdue:")
        print("\u2500" * 60)
        for todo_id, item in due_today_or_overdue.items():
            print_todo(todo_id, item)
    else:
        # Fall back to Eisenhower matrix - show #important + #urgent
        important_urgent = {}
        for todo_id, item in all_todos.items():
            if 'important' in item['tags'] and 'urgent' in item['tags']:
                important_urgent[todo_id] = item

        if important_urgent:
            print("\u26a1 Important & Urgent:")
            print("\u2500" * 60)
            for todo_id, item in important_urgent.items():
                print_todo(todo_id, item)
        else:
            print("No urgent todos found")


def cmd_edit(files: list[str]) -> None:
    """Open all files in default editor"""
    editor = os.environ.get('EDITOR', 'vim')

    unique_files = []
    seen = set()
    for f in files:
        if f not in seen:
            unique_files.append(f)
            seen.add(f)

    try:
        # Redirect stdin to terminal so editor works properly with pipes
        with open('/dev/tty') as tty:
            subprocess.run([editor] + unique_files, stdin=tty, check=True)
    except FileNotFoundError:
        print(f"Error: Editor '{editor}' not found", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nEdit cancelled")

def cmd_add(task_text: str) -> None:
    """Add a new todo item"""
    due_match = re.search(r'due:(\S+)', task_text)
    diary = DiaryDate()

    if due_match:
        due_str = due_match.group(1)
        try:
            due_date = diary.parse(due_str)
            target_file = diary.filepath(due_date, create=True)
        except Exception as e:
            print(f"Error parsing due date: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        target_file = diary.filepath(datetime.now(), create=True)

    # Remove the due:date from task text since the date is stored in the filename
    cleaned_text = re.sub(r'due:\S+\s*', '', task_text).strip()

    # Append todo to file
    with open(target_file, 'a', encoding='utf-8') as f:
        f.write(f"- [ ] {cleaned_text}\n")

    print(f"\u2705 Added to {target_file.name}")
    print(f"   - [ ] {cleaned_text}")


def cmd_send(_files: list[str] = None) -> None:
    """Push the first 7 top-level (non-done, non-indented) todos from today to HA epaper helpers."""
    today_file = str(DiaryDate().filepath(datetime.now()))
    todo = Todo([today_file])
    all_todos = todo.get_all()

    top_level = []
    for item in all_todos.values():
        # Skip done items (belt-and-suspenders: get_all() already excludes [x])
        if re.search(r'\[[xX]\]', item["text"]):
            continue
        # Skip indented subtasks
        if item["text"] != item["text"].lstrip("\t"):
            continue
        text = item["text"].strip()
        text = re.sub(r'^[-*]\s+\[\s*\]\s*', '', text)   # remove checkbox
        text = re.sub(r'\s+due:\S+', '', text)            # remove due:...
        text = re.sub(r'\s+#\w+', '', text)               # remove #tags
        text = re.sub(r'\s+@[\w\s]+', '', text).strip()   # remove @locations
        if text:
            top_level.append(text)
        if len(top_level) == 7:
            break

    print(f"Sending {len(top_level)} todo(s) to Home Assistant (remaining slots will be cleared)...")
    try:
        EPaper().send(top_level)
    except ValueError as e:
        print(f"Config error: {e}", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as e:
        print(f"HA error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_done_interactive(files: list[str]) -> None:
    """Interactive (fzf) todo completion."""
    todo = Todo(files)
    all_todos = todo.get_all()
    if not all_todos:
        print("No todos found")
        return

    # Build id->todo map and display list
    id_map = {}
    display_lines = []
    for tid, item in all_todos.items():
        id_map[tid] = item
        # Minimal display: first 60 chars of text, plus id for internal use
        text = item["text"].strip().replace("- [ ]", "").replace("* [ ]", "").strip()
        display = f"{tid:>4} {text[:60]}"
        display_lines.append(display)

    # Call fzf
    fzf_input = "\n".join(display_lines)
    try:
        result = subprocess.run(
            ["fzf", "--multi", "--preview", "echo {}", "--preview-window=up:1"],
            input=fzf_input,
            text=True,
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        # fzf returned non-zero (user cancelled)
        return

    # Parse selected lines
    selected_lines = result.stdout.strip().splitlines()
    if not selected_lines or selected_lines == [""]:
        return

    # Mark each selected todo done
    for line in selected_lines:
        # line format: "  42 Do the thing..."
        idx_str = line.strip().split()[0]
        try:
            todo_id = int(idx_str)
            if todo_id in id_map:
                todo.mark_todo_done(todo_id)
        except ValueError:
            continue

    # Show remaining todos after marking done
    cmd_show(files)
    cmd_send(files)


def cmd_postpone() -> None:
    """Interactive (fzf) postpone a todo to another day."""
    diary = DiaryDate()
    today = datetime.now()
    today_file = diary.filepath(today)

    if not today_file.exists():
        print("No diary file for today")
        return

    todo = Todo([str(today_file)])
    all_todos = todo.get_all()
    if not all_todos:
        print("No open todos for today")
        return

    # Build display list for first fzf (pick a todo) — top-level tasks only
    id_map = {}
    display_lines = []
    for tid, item in all_todos.items():
        # Skip subtasks (indented items)
        if item["text"] != item["text"].lstrip("\t"):
            continue
        id_map[tid] = item
        text = item["text"].strip().replace("- [ ]", "").replace("* [ ]", "").strip()
        display = f"{tid:>4} {text[:80]}"
        display_lines.append(display)

    if not display_lines:
        print("No open todos for today")
        return

    fzf_input = "\n".join(display_lines)
    try:
        result = subprocess.run(
            ["fzf", "--preview", "echo {}", "--preview-window=up:1"],
            input=fzf_input,
            text=True,
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        return

    selected = result.stdout.strip()
    if not selected:
        return

    idx_str = selected.split()[0]
    try:
        todo_id = int(idx_str)
    except ValueError:
        return
    if todo_id not in id_map:
        return

    item = id_map[todo_id]

    # Build target day options: remaining days this week + "Next week" (Monday)
    today_weekday = today.weekday()  # 0=Monday
    day_options = []
    # Remaining days this week (tomorrow through Sunday)
    for offset in range(1, 7 - today_weekday):
        dt = today + timedelta(days=offset)
        day_options.append((f"{dt.strftime('%A'):<10} {dt.strftime('%Y-%m-%d')}", dt))
    # Next week = next Monday
    next_monday = today + timedelta(days=7 - today_weekday)
    day_options.append((f"{'Next week':<10} {next_monday.strftime('%Y-%m-%d')}", next_monday))

    day_lines = [label for label, _ in day_options]

    fzf_input_days = "\n".join(day_lines)
    try:
        result = subprocess.run(
            ["fzf", "--preview", "echo {}", "--preview-window=up:1"],
            input=fzf_input_days,
            text=True,
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        return

    selected_day = result.stdout.strip()
    if not selected_day:
        return

    # Parse selected date
    date_str = selected_day.split()[-1]
    target_dt = datetime.strptime(date_str, "%Y-%m-%d")
    target_file = diary.filepath(target_dt, create=True)

    # Remove the task + subtasks from today's file
    with open(today_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    line_idx = item["line_number"] - 1
    task_line = lines[line_idx]
    task_indent = len(task_line) - len(task_line.lstrip("\t"))

    # Collect the task + all deeper-indented subtasks below it
    block = [lines[line_idx]]
    end_idx = line_idx + 1
    while end_idx < len(lines):
        line = lines[end_idx]
        if line.strip() == "":
            break
        line_indent = len(line) - len(line.lstrip("\t"))
        if line_indent > task_indent:
            block.append(line)
            end_idx += 1
        else:
            break

    remaining = lines[:line_idx] + lines[end_idx:]

    tmp_path = today_file.with_suffix(today_file.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.writelines(remaining)
    tmp_path.replace(today_file)

    # Append block to target file (dedented to root level)
    with open(target_file, "a", encoding="utf-8") as f:
        for line in block:
            if task_indent > 0 and line[:task_indent] == "\t" * task_indent:
                line = line[task_indent:]
            f.write(line if line.endswith("\n") else line + "\n")

    text = block[0].strip().replace("- [ ]", "").replace("* [ ]", "").strip()
    subtask_count = len(block) - 1
    msg = f"Postponed to {target_file.name}: {text}"
    if subtask_count:
        msg += f" + {subtask_count} subtask(s)"
    print(msg)


def cmd_done_direct(file_path: str, line_number: str) -> None:
    """Mark a specific todo line as done"""
    files = [file_path]
    try:
        line = int(line_number)
        Todo.mark_done(file_path, line)
        print(f"\u2705 Marked line {line_number} in {Path(file_path).name} as done")
        # Show remaining todos from this file
        cmd_show(files)
        cmd_send(files)
    except Exception as e:
        print(f"Error marking done: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    if len(sys.argv) == 2 and sys.argv[1] in ('--version', '-V'):
        from importlib.metadata import version
        print(f"todo {version('todo')}")
        return

    command, files = parse_args()

    if command == 'get':
        cmd_get(files)
    elif command == 'show':
        cmd_show(files)
    elif command == 'edit':
        cmd_edit(files)
    elif command == 'add':
        task_text = ' '.join(sys.argv[2:])
        cmd_add(task_text)
    elif command == 'done':
        if len(sys.argv) >= 4:  # direct mode
            file_path = sys.argv[2]
            line_number = sys.argv[3]
            cmd_done_direct(file_path, line_number)
        else:  # interactive mode
            files_interactive = files or default_files('done')
            if not files_interactive:
                print("Error: No files available for interactive done", file=sys.stderr)
                sys.exit(1)
            cmd_done_interactive(files_interactive)
    elif command == 'postpone':
        cmd_postpone()
    elif command == 'send':
        cmd_send()
    elif command == 'plan':
        if not sys.stdin.isatty():
            plan_files = read_files_from_stdin()
        else:
            plan_files = get_default_files()
        if not plan_files:
            print("No files found to plan from", file=sys.stderr)
            sys.exit(1)
        cmd_plan(plan_files)
    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        print("Commands: get, show, edit, add, done, plan, postpone, send", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
