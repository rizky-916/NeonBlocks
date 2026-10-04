"""High-score persistence.

Security notes
--------------
* The file lives in the per-user data directory, never in the current
  working directory, so running the game from another folder cannot
  overwrite unrelated files.
* Reads are size-limited and the content is strictly validated; a corrupt
  or tampered file is ignored instead of crashing the game.
* Writes are atomic (temporary file + ``os.replace``) so a crash or power
  loss mid-write cannot leave a half-written file behind.
* Only JSON is used; nothing is ever executed or unpickled.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Optional

APP_DIR_NAME = "NeonBlocks"
FILE_NAME = "highscore.json"
MAX_FILE_BYTES = 4096
MAX_SCORE = 10 ** 9


def _absolute_or_none(value: Optional[str]) -> Optional[Path]:
    if value:
        path = Path(value)
        if path.is_absolute():
            return path
    return None


def default_data_dir() -> Path:
    """Platform-appropriate per-user data directory."""
    home = Path.home()
    if os.name == "nt":
        base = _absolute_or_none(os.environ.get("APPDATA")) or home / "AppData" / "Roaming"
    elif sys.platform == "darwin":
        base = home / "Library" / "Application Support"
    else:
        base = _absolute_or_none(os.environ.get("XDG_DATA_HOME")) or home / ".local" / "share"
    return base / APP_DIR_NAME


class HighScoreStore:
    def __init__(self, directory: Optional[Path] = None) -> None:
        self.directory = Path(directory) if directory else default_data_dir()
        self.path = self.directory / FILE_NAME

    def load(self) -> int:
        """Return the saved high score, or 0 if missing or invalid."""
        try:
            if not self.path.is_file() or self.path.stat().st_size > MAX_FILE_BYTES:
                return 0
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.loads(fh.read(MAX_FILE_BYTES))
        except (OSError, ValueError):
            return 0

        if not isinstance(data, dict):
            return 0
        value = data.get("highscore")
        # bool is a subclass of int, so exclude it explicitly.
        if isinstance(value, bool) or not isinstance(value, int):
            return 0
        if not 0 <= value <= MAX_SCORE:
            return 0
        return value

    def save(self, score: int) -> bool:
        """Atomically write the score. Returns False on failure."""
        if isinstance(score, bool) or not isinstance(score, int):
            return False
        score = max(0, min(score, MAX_SCORE))
        tmp_name = None
        try:
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd, tmp_name = tempfile.mkstemp(
                prefix=".highscore-", suffix=".tmp", dir=self.directory
            )
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump({"highscore": score}, fh)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_name, self.path)
            tmp_name = None
            return True
        except OSError as exc:
            print(f"[NeonBlocks] Could not save high score: {exc}", file=sys.stderr)
            return False
        finally:
            if tmp_name and os.path.exists(tmp_name):
                try:
                    os.remove(tmp_name)
                except OSError:
                    pass
