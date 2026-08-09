"""Best-effort private local storage with atomic replacement."""

from __future__ import annotations

import os
from pathlib import Path


def secure_directory(path: str | Path) -> Path:
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(directory, 0o700)
    except OSError:
        pass
    return directory


def secure_file(path: str | Path) -> None:
    try:
        os.chmod(Path(path), 0o600)
    except OSError:
        pass


def write_private(path: str | Path, text: str, *, encoding: str = "utf-8") -> Path:
    target = Path(path)
    secure_directory(target.parent)
    pending = target.with_name(target.name + ".pending")
    pending.write_text(text, encoding=encoding)
    secure_file(pending)
    pending.replace(target)
    secure_file(target)
    return target

