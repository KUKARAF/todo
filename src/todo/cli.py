"""
CLI tool for managing todos from markdown files.

Usage:
    today | todo get                          # Show todos due today or overdue
    today | todo edit                         # Open files in default editor
    week | todo show                          # Print all todos from week
    today | todo done                         # Interactive (fzf) mark done
    todo add "task text #tag @location"       # Add new todo (uses today's file by default)
    todo add "task due:tomorrow #tag"         # Add todo with custom due date
    todo done path/to/file.md 42              # Directly mark line 42 in file as done
"""

import sys
import subprocess
import os
import re
from datetime import datetime
from pathlib import Path
from todo import Todo
from today import DiaryDate
from todo.plan import cmd_plan, get_default_files
from todo.defaults import default_files


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
        print("Commands: get, show, edit, add, done, plan", file=sys.stderr)
        sys.exit(1)

    command = sys.argv[1].lower()

    # 'add', 'done', and 'plan' don't require stdin
    if command in ('add', 'done', 'plan'):
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


def cmd_done_direct(file_path: str, line_number: str) -> None:
    """Mark a specific todo line as done"""
    files = [file_path]
    try:
        line = int(line_number)
        Todo.mark_done(file_path, line)
        print(f"\u2705 Marked line {line_number} in {Path(file_path).name} as done")
        # Show remaining todos from this file
        cmd_show(files)
    except Exception as e:
        print(f"Error marking done: {e}", file=sys.stderr)
        sys.exit(1)


def main():
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
        print("Commands: get, show, edit, add, done, plan", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
