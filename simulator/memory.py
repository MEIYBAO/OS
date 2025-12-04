from collections import deque
from typing import Dict, List, Optional, Tuple

from .models import Process


class MemoryManager:
    """Simple paged memory manager with FIFO replacement."""

    def __init__(self, frames: int = 20):
        self.frames = frames
        self.frame_table: List[Optional[Tuple[int, int]]] = [None for _ in range(frames)]
        self.replacement_queue: deque[int] = deque(range(frames))
        self.page_locations: Dict[Tuple[int, int], int] = {}
        self.last_access: Optional[int] = None

    def access_page(self, process: Process, page: int) -> Tuple[bool, int, Optional[Tuple[int, int]]]:
        """
        Returns (page_fault, frame, evicted_page).
        evicted_page is (pid, page) when a page is replaced.
        """
        normalized = page % max(process.memory_pages, 1)
        key = (process.pid, normalized)
        if key in self.page_locations:
            frame = self.page_locations[key]
            self.last_access = frame
            return False, frame, None

        frame = self.replacement_queue.popleft()
        evicted: Optional[Tuple[int, int]] = self.frame_table[frame]
        if evicted and evicted in self.page_locations:
            del self.page_locations[evicted]
        self.frame_table[frame] = key
        self.page_locations[key] = frame
        self.replacement_queue.append(frame)
        self.last_access = frame
        process.page_table[normalized] = frame
        return True, frame, evicted

    def reset(self) -> None:
        self.frame_table = [None for _ in range(self.frames)]
        self.replacement_queue = deque(range(self.frames))
        self.page_locations.clear()
        self.last_access = None
