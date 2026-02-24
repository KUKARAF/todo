"""Default file resolution when no files are piped via stdin."""

from datetime import datetime
from today import DiaryDate


def default_files(command: str) -> list[str]:
    """Return default file paths for a command when stdin is not provided."""
    diary = DiaryDate()

    if command == "edit":
        path = diary.filepath(datetime.now(), create=True)
        return [str(path)]

    if command == "get":
        path = diary.filepath(datetime.now(), create=True)
        return [str(path)]

    if command == "show":
        return [str(p) for p in diary.week_files()]

    if command == "done":
        path = diary.filepath(datetime.now())
        if path.exists():
            return [str(path)]
        return []

    return []
