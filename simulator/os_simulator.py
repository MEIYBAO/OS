from __future__ import annotations

from collections import deque
from typing import Deque, Dict, List, Optional

from .filesystem import FileSystem
from .memory import MemoryManager
from .models import Process, ProcessAction


class OSSimulator:
    """Tie together scheduling, memory, files, and process lifecycle."""

    def __init__(self, time_quantum: int = 2):
        self.time_quantum = time_quantum
        self.clock: int = 0
        self.process_pool: Dict[int, Process] = {}
        self.ready_queue: Deque[Process] = deque()
        self.blocked: List[Process] = []
        self.finished: List[Process] = []
        self.running: Optional[Process] = None
        self.memory = MemoryManager(frames=8)
        self.file_system = FileSystem()
        self.event_log: List[str] = []
        self.templates = self._default_templates()

    def _default_templates(self) -> List[Process]:
        """Predefined scripts to show OS concepts deterministically."""
        return [
            Process(
                pid=1,
                name="编译任务",
                arrival_time=0,
                memory_pages=6,
                actions=[
                    ProcessAction("cpu", "编译器装载"),
                    ProcessAction("mem", "访问代码段", page=0),
                    ProcessAction("mem", "访问数据段", page=1),
                    ProcessAction("file_create", "生成中间文件", path="/build/tmp.o", size=4),
                    ProcessAction("cpu", "语法分析"),
                    ProcessAction("io", "等待磁盘写入", io_duration=2),
                    ProcessAction("mem", "访问新的代码页", page=4),
                    ProcessAction("cpu", "指令优化"),
                    ProcessAction("file_write", "写入目标文件", path="/build/app", size=6),
                    ProcessAction("cpu", "收尾"),
                ],
            ),
            Process(
                pid=2,
                name="数据库",
                arrival_time=1,
                memory_pages=5,
                actions=[
                    ProcessAction("cpu", "接收查询"),
                    ProcessAction("mem", "访问索引页", page=2),
                    ProcessAction("file_read", "读取数据页", path="/data/users", size=2),
                    ProcessAction("cpu", "计算聚合"),
                    ProcessAction("io", "等待磁盘", io_duration=1),
                    ProcessAction("mem", "访问缓存页", page=3),
                    ProcessAction("cpu", "返回结果"),
                ],
            ),
            Process(
                pid=3,
                name="备份程序",
                arrival_time=3,
                memory_pages=4,
                actions=[
                    ProcessAction("file_create", "创建日志", path="/backup/log", size=1),
                    ProcessAction("mem", "扫描页", page=0),
                    ProcessAction("cpu", "压缩数据"),
                    ProcessAction("file_write", "写入镜像", path="/backup/image", size=8),
                    ProcessAction("io", "写入磁盘", io_duration=2),
                    ProcessAction("mem", "校验页", page=2),
                    ProcessAction("file_delete", "删除旧镜像", path="/backup/old"),
                    ProcessAction("cpu", "收尾"),
                ],
            ),
        ]

    def reset(self) -> None:
        self.clock = 0
        self.process_pool = {proc.pid: self._clone_process(proc) for proc in self.templates}
        self.ready_queue.clear()
        self.blocked.clear()
        self.finished.clear()
        self.running = None
        self.memory.reset()
        self.file_system.reset()
        self.event_log.clear()

    def _clone_process(self, template: Process) -> Process:
        return Process(
            pid=template.pid,
            name=template.name,
            arrival_time=template.arrival_time,
            actions=list(template.actions),
            memory_pages=template.memory_pages,
        )

    def _log(self, message: str) -> None:
        self.event_log.append(f"[t={self.clock}] {message}")

    def _dispatch_if_needed(self) -> None:
        if self.running is None and self.ready_queue:
            self.running = self.ready_queue.popleft()
            self.running.state = "Running"
            self.running.reset_runtime()
            self._log(f"调度进程 {self.running.pid} ({self.running.name}) 运行。")

    def _handle_blocked(self) -> None:
        newly_ready = [p for p in self.blocked if p.tick_block()]
        self.blocked = [p for p in self.blocked if p.state == "Blocked"]
        for proc in newly_ready:
            self.ready_queue.append(proc)
            self._log(f"进程 {proc.pid} I/O 完成，重新进入就绪队列。")

    def _complete_process(self, proc: Process) -> None:
        proc.finish()
        self.finished.append(proc)
        self._log(f"进程 {proc.pid} 已完成全部动作。")
        self.running = None

    def _preempt(self, proc: Process) -> None:
        proc.state = "Ready"
        proc.current_quantum = 0
        self.ready_queue.append(proc)
        self._log(f"进程 {proc.pid} 时间片用完，被重新排入就绪队列。")
        self.running = None

    def _block(self, proc: Process, duration: int) -> None:
        proc.mark_blocked(duration)
        self.blocked.append(proc)
        self._log(f"进程 {proc.pid} 阻塞，等待 {duration} 个时间片。")
        self.running = None

    def _execute_memory(self, proc: Process, action: ProcessAction) -> None:
        fault, frame, evicted = self.memory.access_page(proc, action.page or 0)
        if fault:
            if evicted:
                evicted_pid, evicted_page = evicted
                owner = self.process_pool.get(evicted_pid)
                if owner:
                    owner.page_table.pop(evicted_page, None)
            evicted_text = f"，淘汰页 {evicted}" if evicted else ""
            self._log(
                f"进程 {proc.pid} 访问虚页 {action.page} 发生缺页，装入帧 {frame}{evicted_text}。"
            )
        else:
            self._log(f"进程 {proc.pid} 命中物理帧 {frame}。")

    def _execute_file_action(self, proc: Process, action: ProcessAction) -> None:
        if action.kind == "file_create":
            message = self.file_system.create(action.path or "", proc.pid, size=action.size or 0)
        elif action.kind == "file_write":
            message = self.file_system.write(action.path or "", proc.pid, size=action.size or 0)
        elif action.kind == "file_read":
            message = self.file_system.read(action.path or "", proc.pid)
        elif action.kind == "file_delete":
            message = self.file_system.delete(action.path or "", proc.pid)
        else:
            message = "未知文件操作"
        self._log(message)

    def _run_action(self, proc: Process) -> None:
        action = proc.next_action()
        if action is None:
            self._complete_process(proc)
            return

        self._log(f"进程 {proc.pid}：{action.description}")
        if action.kind == "cpu":
            pass
        elif action.kind == "io":
            proc.advance()
            self._block(proc, action.io_duration or 1)
            return
        elif action.kind == "mem":
            self._execute_memory(proc, action)
        elif action.kind.startswith("file"):
            self._execute_file_action(proc, action)
        else:
            self._log(f"进程 {proc.pid} 执行未知操作 {action.kind}")

        proc.advance()
        if proc.remaining_actions == 0:
            self._complete_process(proc)
            return

        proc.current_quantum += 1
        if proc.current_quantum >= self.time_quantum:
            self._preempt(proc)

    def step(self) -> None:
        self.clock += 1
        self._log("===== 时钟跳动 =====")

        for proc in list(self.process_pool.values()):
            if proc.state == "New" and proc.arrival_time <= self.clock:
                proc.state = "Ready"
                self.ready_queue.append(proc)
                self._log(f"新进程 {proc.pid} ({proc.name}) 到达并进入就绪队列。")

        self._handle_blocked()
        self._dispatch_if_needed()
        if self.running:
            self._run_action(self.running)
        else:
            self._log("处理器空闲。")

    def snapshot(self) -> Dict[str, object]:
        return {
            "clock": self.clock,
            "running": self.running,
            "ready": list(self.ready_queue),
            "blocked": list(self.blocked),
            "finished": list(self.finished),
            "frames": self.memory.frame_table,
            "last_access": self.memory.last_access,
            "files": self.file_system.files,
            "log": list(self.event_log[-8:]),
        }
