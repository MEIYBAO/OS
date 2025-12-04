from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ProcessAction:
    """A single step a process can perform in the simulation."""

    kind: str
    description: str
    page: Optional[int] = None
    path: Optional[str] = None
    size: Optional[int] = None
    io_duration: int = 0


@dataclass
class Process:
    pid: int
    name: str
    arrival_time: int
    actions: List[ProcessAction]
    memory_pages: int
    state: str = "New"
    pointer: int = 0
    current_quantum: int = 0
    io_timer: int = 0
    queue_level: int = 0
    wait_reason: str = ""
    page_table: dict = field(default_factory=dict)

    def next_action(self) -> Optional[ProcessAction]:
        if self.pointer < len(self.actions):
            return self.actions[self.pointer]
        return None

    def advance(self) -> None:
        self.pointer += 1

    @property
    def remaining_actions(self) -> int:
        return max(len(self.actions) - self.pointer, 0)

    def mark_blocked(self, duration: int) -> None:
        self.state = "Blocked"
        self.io_timer = duration
        self.current_quantum = 0
        self.wait_reason = ""

    def mark_wait(self, reason: str) -> None:
        self.state = "Blocked"
        self.wait_reason = reason
        self.current_quantum = 0

    def tick_block(self) -> bool:
        if self.io_timer > 0:
            self.io_timer -= 1
        if self.io_timer == 0:
            if not self.wait_reason:
                self.state = "Ready"
                return True
        return False

    def ready_from_wait(self) -> None:
        self.wait_reason = ""
        self.state = "Ready"

    def finish(self) -> None:
        self.state = "Finished"
        self.current_quantum = 0

    def reset_runtime(self) -> None:
        self.current_quantum = 0
