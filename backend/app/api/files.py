"""What an uploaded file is allowed to be called once Tarazu holds it.

A filename arrives from the browser or from an integration, and it becomes
part of a storage path, a `Content-Disposition` header, a trail entry, and a
report row. None of those should ever see a directory separator, a control
character, or a name too long for the filesystem — a file called
`../../etc/passwd.csv` is a ledger to the reader and an attack to the store.

`safe_filename` keeps the part a person recognises (the name and its
extension) and nothing else. `suffix_of` reads the extension the same way
everywhere the accepted-formats list is checked.
"""

from __future__ import annotations

import re

__all__ = ["MAX_FILENAME_LENGTH", "safe_filename", "suffix_of"]

#: Long enough for any name a person would type; short enough for every
#: filesystem and object store Tarazu writes to.
MAX_FILENAME_LENGTH = 150

#: Separators, control characters, and the characters Windows refuses in a
#: name. Each run becomes one underscore.
_UNSAFE = re.compile(r"[\\/\x00-\x1f\x7f<>:\"|?*]+")


def suffix_of(filename: str | None) -> str:
    """`.csv` for `Ledger.CSV`; `""` when there is no extension."""
    if not filename or "." not in filename:
        return ""
    return "." + filename.rsplit(".", 1)[1].lower()


def safe_filename(raw: str | None) -> str:
    """The name Tarazu stores a file under: its own basename, made harmless.

    - Only the last path segment survives, whichever separator was used.
    - Separators, control characters, and Windows-reserved characters become
      underscores; surrounding whitespace and dots go.
    - A name over `MAX_FILENAME_LENGTH` is cut from the stem, keeping the
      extension the readers key on.
    - Nothing left means `unnamed`.
    """
    name = (raw or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = _UNSAFE.sub("_", name).strip(" .\t")
    if len(name) > MAX_FILENAME_LENGTH:
        stem, dot, extension = name.rpartition(".")
        if dot and 0 < len(extension) <= 10:
            keep = MAX_FILENAME_LENGTH - len(extension) - 1
            name = f"{stem[:keep].rstrip(' .')}.{extension}"
        else:
            name = name[:MAX_FILENAME_LENGTH].rstrip(" .")
    return name or "unnamed"
