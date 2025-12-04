from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class FileEntry:
    owner: int
    size: int
    content: str


class FileSystem:
    """A tiny in-memory file system to visualize file operations."""

    def __init__(self):
        self.files: Dict[str, FileEntry] = {}

    def create(self, path: str, owner: int, size: int = 0) -> str:
        if path in self.files:
            return f"文件 {path} 已存在，覆盖旧数据。"
        self.files[path] = FileEntry(owner=owner, size=size, content="" * size)
        return f"进程 {owner} 创建文件 {path}，初始大小 {size}KB。"

    def write(self, path: str, owner: int, size: int) -> str:
        entry = self.files.get(path)
        if not entry:
            self.files[path] = FileEntry(owner=owner, size=size, content="" * size)
            return f"进程 {owner} 向新文件 {path} 写入 {size}KB。"
        entry.size += size
        entry.content += "#" * size
        return f"进程 {owner} 扩展文件 {path}，增加 {size}KB。"

    def read(self, path: str, owner: int) -> str:
        if path not in self.files:
            return f"进程 {owner} 读取 {path} 失败：文件不存在。"
        entry = self.files[path]
        return f"进程 {owner} 读取 {path}，大小 {entry.size}KB。"

    def delete(self, path: str, owner: int) -> str:
        if path not in self.files:
            return f"进程 {owner} 删除 {path} 失败：文件不存在。"
        del self.files[path]
        return f"进程 {owner} 删除文件 {path}。"

    def reset(self) -> None:
        self.files.clear()
