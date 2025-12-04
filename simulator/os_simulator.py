from __future__ import annotations

from collections import deque
from typing import Deque, Dict, List, Optional, Tuple

from .filesystem import FileSystem
from .memory import MemoryManager
from .models import Process, ProcessAction


class OSSimulator:
    """Tie together scheduling, memory, files, and process lifecycle."""

    def __init__(self, time_quantum: int = 2):
        self.time_quantum = time_quantum
        self.clock: int = 0
        self.process_pool: Dict[int, Process] = {}
        self.ready_queues: List[Deque[Process]] = [deque(), deque(), deque()]
        self.blocked: List[Process] = []
        self.finished: List[Process] = []
        self.running: Optional[Process] = None
        self.memory = MemoryManager(frames=20)
        self.file_system = FileSystem()
        self.event_log: List[str] = []
        self.buffer_capacity = 5
        self.buffer_slots: List[Optional[int]] = [None] * self.buffer_capacity
        self.buffer_in = 0
        self.buffer_out = 0
        self.buffer_count = 0
        self.mutex_owner: Optional[int] = None
        self.shared_resources: Dict[str, int] = {"磁带机": 1, "GPU": 1, "打印机": 2}
        self.queue_quantums = [1, 2, 4]
        self.templates = self._default_templates()
        self.dynamic_templates = self._dynamic_templates()
        self.next_pid = len(self.templates) + 1

    def _default_templates(self) -> List[Process]:
        """Predefined scripts to show OS concepts deterministically."""
        return [
            Process(
                pid=1,
                name="生产者A",
                arrival_time=0,
                memory_pages=3,
                actions=[
                    ProcessAction("produce", "申请互斥并生产一件产品"),
                    ProcessAction("mem", "访问代码页", page=0),
                    ProcessAction("produce", "继续生产填充缓冲区"),
                    ProcessAction("produce", "生产更多数据"),
                    ProcessAction("cpu", "计算校验码"),
                    ProcessAction("produce", "尝试再放入一件"),
                    ProcessAction("produce", "再次填充，可能触发满等待"),
                ],
            ),
            Process(
                pid=2,
                name="消费者B",
                arrival_time=0,
                memory_pages=3,
                actions=[
                    ProcessAction("consume", "申请互斥并消费一件产品"),
                    ProcessAction("mem", "访问数据页", page=1),
                    ProcessAction("consume", "继续消费"),
                    ProcessAction("io", "输出结果", io_duration=1),
                    ProcessAction("consume", "再次消费"),
                    ProcessAction("consume", "直到缓冲区空，可能阻塞"),
                ],
            ),
            Process(
                pid=3,
                name="生产者C",
                arrival_time=1,
                memory_pages=3,
                actions=[
                    ProcessAction("produce", "批量生产，补充库存"),
                    ProcessAction("produce", "继续生产"),
                    ProcessAction("mem", "更新生产统计", page=1),
                    ProcessAction("produce", "再放入一件"),
                    ProcessAction("cpu", "计算下一批计划"),
                    ProcessAction("produce", "补齐缓冲，可能等待空位"),
                ],
            ),
            Process(
                pid=4,
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
                    ProcessAction("res_acquire", "占用磁带机写出", resource="磁带机"),
                    ProcessAction("cpu", "收尾"),
                    ProcessAction("res_release", "释放磁带机", resource="磁带机"),
                ],
            ),
            Process(
                pid=5,
                name="消费者D",
                arrival_time=2,
                memory_pages=2,
                actions=[
                    ProcessAction("consume", "尝试消费产品，可能等待"),
                    ProcessAction("mem", "访问缓存页", page=1),
                    ProcessAction("consume", "继续消费清空缓冲"),
                    ProcessAction("consume", "再次消费"),
                ],
            ),
            Process(
                pid=6,
                name="数据库",
                arrival_time=2,
                memory_pages=5,
                actions=[
                    ProcessAction("cpu", "接收查询"),
                    ProcessAction("mem", "访问索引页", page=2),
                    ProcessAction("file_read", "读取数据页", path="/data/users", size=2),
                    ProcessAction("cpu", "计算聚合"),
                    ProcessAction("res_acquire", "申请GPU并执行加速", resource="GPU"),
                    ProcessAction("io", "等待磁盘", io_duration=1),
                    ProcessAction("mem", "访问缓存页", page=3),
                    ProcessAction("res_release", "释放GPU", resource="GPU"),
                    ProcessAction("cpu", "返回结果"),
                ],
            ),
        ]

    def _dynamic_templates(self) -> List[List[ProcessAction]]:
        return [
            [
                ProcessAction("cpu", "短作业计算"),
                ProcessAction("mem", "访存页", page=0),
                ProcessAction("cpu", "快速结束"),
            ],
            [
                ProcessAction("res_acquire", "申请打印机生成报表", resource="打印机"),
                ProcessAction("cpu", "格式化报表"),
                ProcessAction("mem", "加载模板页", page=2),
                ProcessAction("res_release", "释放打印机", resource="打印机"),
            ],
            [
                ProcessAction("mem", "预取代码页", page=1),
                ProcessAction("io", "等待网络", io_duration=1),
                ProcessAction("file_read", "读取配置", path="/etc/conf", size=1),
                ProcessAction("cpu", "处理请求"),
            ],
        ]

    def reset(self) -> None:
        self.clock = 0
        self.process_pool = {proc.pid: self._clone_process(proc) for proc in self.templates}
        for q in self.ready_queues:
            q.clear()
        self.blocked.clear()
        self.finished.clear()
        self.running = None
        self.memory.reset()
        self.file_system.reset()
        self.event_log.clear()
        self.buffer_slots = [None] * self.buffer_capacity
        self.buffer_in = 0
        self.buffer_out = 0
        self.buffer_count = 0
        self.mutex_owner = None
        self.next_pid = len(self.templates) + 1

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

    def _spawn_dynamic_job(self) -> None:
        index = (self.clock // 3) % len(self.dynamic_templates)
        actions = [
            ProcessAction(a.kind, a.description, a.page, a.path, a.size, a.io_duration, a.resource)
            for a in self.dynamic_templates[index]
        ]
        proc = Process(
            pid=self.next_pid,
            name=f"新作业{self.next_pid}",
            arrival_time=self.clock,
            memory_pages=3,
            actions=actions,
        )
        self.process_pool[proc.pid] = proc
        self.next_pid += 1
        proc.state = "Ready"
        proc.queue_level = 0
        self.ready_queues[0].append(proc)
        self._log(f"自动生成新进程 {proc.pid} 插入就绪队列，保持持续负载。")

    def _dispatch_if_needed(self) -> None:
        if self.running is None:
            for level, queue in enumerate(self.ready_queues):
                if queue:
                    self.running = queue.popleft()
                    self.running.state = "Running"
                    self.running.reset_runtime()
                    self.running.queue_level = level
                    self._log(
                        f"调度进程 {self.running.pid} 进入CPU（队列Q{level}, 时间片 {self.queue_quantums[level]}）。"
                    )
                    break

    def _handle_blocked(self) -> None:
        newly_ready: List[Tuple[Process, str]] = []
        for proc in list(self.blocked):
            if proc.wait_reason:
                if self._can_wake_from_wait(proc):
                    reason = proc.wait_reason
                    proc.ready_from_wait()
                    newly_ready.append((proc, reason))
            elif proc.tick_block():
                newly_ready.append((proc, ""))
        self.blocked = [p for p in self.blocked if p.state == "Blocked"]
        for proc, reason in newly_ready:
            proc.queue_level = 0
            self.ready_queues[proc.queue_level].append(proc)
            if reason:
                self._log(f"进程 {proc.pid} 获得{reason}，回到高优先级队列。")
            else:
                self._log(f"进程 {proc.pid} I/O 完成，重新进入高优先级队列。")

    def _complete_process(self, proc: Process) -> None:
        proc.finish()
        self.finished.append(proc)
        self._log(f"进程 {proc.pid} 已完成全部动作。")
        self.running = None

    def _preempt(self, proc: Process) -> None:
        proc.state = "Ready"
        proc.current_quantum = 0
        proc.queue_level = min(proc.queue_level + 1, len(self.ready_queues) - 1)
        self.ready_queues[proc.queue_level].append(proc)
        self._log(f"进程 {proc.pid} 时间片用完，降到队列 Q{proc.queue_level}。")
        self.running = None

    def _block(self, proc: Process, duration: int) -> None:
        proc.mark_blocked(duration)
        self.blocked.append(proc)
        self._log(f"进程 {proc.pid} 阻塞，等待 {duration} 个时间片。")
        self.running = None

    def _block_reason(self, proc: Process, reason: str) -> None:
        proc.mark_wait(reason)
        self.blocked.append(proc)
        self._log(f"进程 {proc.pid} 因 {reason} 阻塞，等待资源。")
        self.running = None

    def _can_wake_from_wait(self, proc: Process) -> bool:
        if proc.wait_reason == "等待空槽":
            return self.buffer_count < self.buffer_capacity
        if proc.wait_reason == "等待产品":
            return self.buffer_count > 0
        if proc.wait_reason == "等待互斥锁":
            return self.mutex_owner is None
        if proc.wait_reason.startswith("等待资源"):
            resource = proc.wait_reason.replace("等待资源", "")
            return self.shared_resources.get(resource, 0) > 0
        return False

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

    def _with_mutex(self, proc: Process) -> bool:
        if self.mutex_owner is None:
            self.mutex_owner = proc.pid
            return True
        if self.mutex_owner == proc.pid:
            return True
        self._block_reason(proc, "等待互斥锁")
        return False

    def _release_mutex(self, proc: Process) -> None:
        if self.mutex_owner == proc.pid:
            self.mutex_owner = None

    def _execute_pc_action(self, proc: Process, action: ProcessAction) -> None:
        if not self._with_mutex(proc):
            return
        if action.kind == "produce":
            if self.buffer_count >= self.buffer_capacity:
                self._release_mutex(proc)
                self._block_reason(proc, "等待空槽")
                return
            self.buffer_slots[self.buffer_in] = proc.pid
            slot = self.buffer_in
            self.buffer_in = (self.buffer_in + 1) % self.buffer_capacity
            self.buffer_count += 1
            self._log(
                f"进程 {proc.pid} 生产 1 件产品放入槽位 {slot}，缓冲区 {self.buffer_count}/{self.buffer_capacity}。",
            )
        elif action.kind == "consume":
            if self.buffer_count <= 0:
                self._release_mutex(proc)
                self._block_reason(proc, "等待产品")
                return
            owner = self.buffer_slots[self.buffer_out]
            slot = self.buffer_out
            self.buffer_slots[self.buffer_out] = None
            self.buffer_out = (self.buffer_out + 1) % self.buffer_capacity
            self.buffer_count -= 1
            who = f"(来自P{owner})" if owner is not None else ""
            self._log(
                f"进程 {proc.pid} 消费槽位 {slot} 的产品{who}，缓冲区 {self.buffer_count}/{self.buffer_capacity}。",
            )
        self._release_mutex(proc)

    def _execute_resource_action(self, proc: Process, action: ProcessAction) -> None:
        resource = action.resource or "未知资源"
        if action.kind == "res_acquire":
            if self.shared_resources.get(resource, 0) <= 0:
                self._block_reason(proc, f"等待资源{resource}")
                return
            self.shared_resources[resource] -= 1
            self._log(f"进程 {proc.pid} 获取资源 {resource}，剩余 {self.shared_resources[resource]}。")
        else:
            self.shared_resources[resource] = self.shared_resources.get(resource, 0) + 1
            self._log(f"进程 {proc.pid} 释放资源 {resource}，可用 {self.shared_resources[resource]}。")

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
        elif action.kind in {"produce", "consume"}:
            self._execute_pc_action(proc, action)
            if proc.state == "Blocked":
                return
        elif action.kind.startswith("file"):
            self._execute_file_action(proc, action)
        elif action.kind.startswith("res_"):
            self._execute_resource_action(proc, action)
            if proc.state == "Blocked":
                return
        else:
            self._log(f"进程 {proc.pid} 执行未知操作 {action.kind}")

        proc.advance()
        if proc.remaining_actions == 0:
            self._complete_process(proc)
            return

        proc.current_quantum += 1
        if proc.current_quantum >= self.queue_quantums[proc.queue_level]:
            self._preempt(proc)

    def step(self) -> None:
        self.clock += 1
        self._log("===== 时钟跳动 =====")

        for proc in list(self.process_pool.values()):
            if proc.state == "New" and proc.arrival_time <= self.clock:
                proc.state = "Ready"
                proc.queue_level = 0
                self.ready_queues[0].append(proc)
                self._log(f"新进程 {proc.pid} ({proc.name}) 到达并进入就绪队列 Q0。")

        self._handle_blocked()
        self._dispatch_if_needed()
        if self.running:
            self._run_action(self.running)
        else:
            self._log("处理器空闲。")

        if self.clock % 4 == 0:
            self._spawn_dynamic_job()

    def snapshot(self) -> Dict[str, object]:
        return {
            "clock": self.clock,
            "running": self.running,
            "ready": [list(q) for q in self.ready_queues],
            "blocked": list(self.blocked),
            "finished": list(self.finished),
            "frames": self.memory.frame_table,
            "last_access": self.memory.last_access,
            "page_tables": {pid: proc.page_table for pid, proc in self.process_pool.items()},
            "process_meta": {
                pid: {"name": proc.name, "memory_pages": proc.memory_pages}
                for pid, proc in self.process_pool.items()
            },
            "files": self.file_system.files,
            "buffer": {
                "used": self.buffer_count,
                "capacity": self.buffer_capacity,
                "slots": list(self.buffer_slots),
                "in": self.buffer_in,
                "out": self.buffer_out,
            },
            "log": list(self.event_log),
        }
