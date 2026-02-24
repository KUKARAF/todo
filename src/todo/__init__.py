import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional


class Todo:
    def __init__(self, md_files: List[str]):
        """
        Initialize Todo with a list of markdown file paths.

        Args:
            md_files: List of markdown file paths (e.g., ['/path/2026-01-11.md'])
        """
        self.todos: Dict[int, dict] = {}
        self._id_counter = 0
        self._load_todos(md_files)

    def _get_file_date(self, file_path: str) -> datetime:
        """Extract date from filename (format: YYYY-MM-DD.md). Returns datetime at midnight."""
        match = re.search(r'(\d{4})-(\d{2})-(\d{2})', file_path)
        if match:
            try:
                return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            except ValueError:
                return datetime.now()
        return datetime.now()

    def _parse_due_date(self, due_str: str, reference_date: datetime) -> Optional[datetime]:
        """Parse due date string using timefhuman with reference_date as context."""
        try:
            from timefhuman import timefhuman

            # Use 'now' parameter for timefhuman
            results = timefhuman(due_str, now=reference_date)
            if results:
                # Handle various return types from timefhuman
                result = results[0] if isinstance(results, list) else results

                # If it's a tuple (range), return the start time
                if isinstance(result, tuple):
                    return result[0]
                # If it's a list (alternatives), return the first
                elif isinstance(result, list):
                    first = result[0]
                    return first[0] if isinstance(first, tuple) else first
                # Otherwise it's a datetime
                else:
                    return result
        except Exception:
            # Fallback if timefhuman fails to parse
            return None

    def _extract_tags(self, text: str) -> List[str]:
        """Extract all #tag mentions from text"""
        return re.findall(r'#(\w+)', text)

    def _extract_locations(self, text: str) -> List[str]:
        """Extract all @location mentions from text"""
        return re.findall(r'@([\w\s]+)', text)

    def _extract_due_date(self, text: str) -> Optional[str]:
        """Extract due:... from text"""
        match = re.search(r'due:(.+?)(?:\s+[#@]|\s*$)', text)
        if match:
            return match.group(1).strip()
        return None

    def _load_todos(self, md_files: List[str]) -> None:
        """Load todos from markdown files and extract all attributes"""
        for file_path in md_files:
            path = Path(file_path)
            if not path.exists():
                continue

            file_date = self._get_file_date(str(path))

            with open(path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    # Match lines starting with - [ ] or * [ ] (unchecked todos)
                    if re.match(r'^\s*[-*]\s+\[\s*\]\s+', line):
                        todo_text = line.rstrip()

                        # Extract attributes
                        tags = self._extract_tags(todo_text)
                        locations = self._extract_locations(todo_text)
                        due_str = self._extract_due_date(todo_text)
                        due_date = None

                        if due_str:
                            due_date = self._parse_due_date(due_str, file_date)

                        # Create todo item dict
                        self.todos[self._id_counter] = {
                            'text': todo_text,
                            'file': str(path),
                            'line_number': line_num,
                            'tags': tags,
                            'locations': locations,
                            'due_date': due_date
                        }
                        self._id_counter += 1

    def get_all(self) -> Dict[int, dict]:
        """Return all todos"""
        return self.todos.copy()

    def mark_todo_done(self, todo_id: int) -> None:
        """
        Mark the todo identified by todo_id as done by looking up the file
        and line number that were captured at load time.
        """
        if todo_id not in self.todos:
            raise KeyError(f"todo_id {todo_id} not found")
        item = self.todos[todo_id]
        self.mark_done(item['file'], item['line_number'])

    @staticmethod
    def mark_done(file_path: str, line_number: int) -> None:
        """
        Mark the todo on the given line in the specified file as done by changing
        '- [ ]' or '* [ ]' to '- [x]' or '* [x]' respectively.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Read all lines
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # Validate line number
        if line_number < 1 or line_number > len(lines):
            raise ValueError(f"Line number {line_number} out of range (1-{len(lines)})")

        # Zero-based index for list access
        idx = line_number - 1

        # Only rewrite unchecked todos
        original_line = lines[idx].rstrip("\n")
        updated_line = re.sub(r'^(\s*[-*]\s+)\[\s*\](\s+.*)$', r'\1[x]\2', original_line)

        if updated_line == original_line:
            # No substitution took place; line is either already checked or not a todo
            return

        lines[idx] = updated_line + "\n"

        # Write back atomically
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        tmp_path.replace(path)
