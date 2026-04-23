from __future__ import annotations
import re
from dataclasses import dataclass

# Matches both legacy (#!) and new (/file/) MEGA public links.
_LEGACY_FILE_RE = re.compile(
    r"mega\.nz/#!([A-Za-z0-9_-]+)!([A-Za-z0-9_-]+)"
)
_NEW_FILE_RE = re.compile(
    r"mega\.nz/file/([A-Za-z0-9_-]+)#([A-Za-z0-9_-]+)"
)
_LEGACY_FOLDER_RE = re.compile(
    r"mega\.nz/#F!([A-Za-z0-9_-]+)!([A-Za-z0-9_-]+)"
)
_NEW_FOLDER_RE = re.compile(
    r"mega\.nz/folder/([A-Za-z0-9_-]+)#([A-Za-z0-9_-]+)"
)
# Single file within a folder: mega.nz/folder/FID#FKEY/file/FID#FKEY
_FOLDER_FILE_RE = re.compile(
    r"mega\.nz/folder/([A-Za-z0-9_-]+)#([A-Za-z0-9_-]+)/file/([A-Za-z0-9_-]+)#([A-Za-z0-9_-]+)"
)

@dataclass
class FileLink:
    kind: str = "file"
    file_id: str = ""
    file_key_b64: str = ""

@dataclass
class FolderLink:
    kind: str = "folder"
    folder_id: str = ""
    folder_key_b64: str = ""

@dataclass
class FolderFileLink:
    kind: str = "folder-file"
    folder_id: str = ""
    folder_key_b64: str = ""
    file_id: str = ""
    file_key_b64: str = ""

def parse_link(url: str) -> FileLink | FolderLink | FolderFileLink:
    if (m := _FOLDER_FILE_RE.search(url)):
        return FolderFileLink(
            folder_id=m.group(1), folder_key_b64=m.group(2),
            file_id=m.group(3), file_key_b64=m.group(4),
        )
    if (m := _LEGACY_FOLDER_RE.search(url)):
        return FolderLink(folder_id=m.group(1), folder_key_b64=m.group(2))
    if (m := _NEW_FOLDER_RE.search(url)):
        return FolderLink(folder_id=m.group(1), folder_key_b64=m.group(2))
    if (m := _LEGACY_FILE_RE.search(url)):
        return FileLink(file_id=m.group(1), file_key_b64=m.group(2))
    if (m := _NEW_FILE_RE.search(url)):
        return FileLink(file_id=m.group(1), file_key_b64=m.group(2))
    raise ValueError(f"unrecognized MEGA link: {url}")
