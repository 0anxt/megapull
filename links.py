from __future__ import annotations
import re
from dataclasses import dataclass

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
    sub_file_id: str | None = None

_NEW_FILE = re.compile(r"mega\.nz/file/([A-Za-z0-9_-]+)#([A-Za-z0-9_-]+)")
_OLD_FILE = re.compile(r"mega\.nz/#!([A-Za-z0-9_-]+)!([A-Za-z0-9_-]+)")
_NEW_FOLDER = re.compile(
    r"mega\.nz/folder/([A-Za-z0-9_-]+)#([A-Za-z0-9_-]+)(?:/file/([A-Za-z0-9_-]+))?"
)
_OLD_FOLDER = re.compile(
    r"mega\.nz/#F!([A-Za-z0-9_-]+)!([A-Za-z0-9_-]+)(?:!([A-Za-z0-9_-]+))?"
)

def parse_link(url: str):
    for rx, folder in ((_NEW_FOLDER, True), (_OLD_FOLDER, True),
                      (_NEW_FILE, False), (_OLD_FILE, False)):
        m = rx.search(url)
        if not m:
            continue
        if folder:
            fid, key, sub = m.group(1), m.group(2), (
                m.group(3) if m.lastindex and m.lastindex >= 3 else None
            )
            return FolderLink(folder_id=fid, folder_key_b64=key, sub_file_id=sub)
        return FileLink(file_id=m.group(1), file_key_b64=m.group(2))
    raise ValueError(f"not a recognizable MEGA link: {url}")
