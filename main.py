import math
import tkinter as tk
from tkinter import scrolledtext, ttk

from simulator.os_simulator import OSSimulator


class SimulatorGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("操作系统可视化模拟器")
        self.simulator = OSSimulator(time_quantum=2)
        self.simulator.reset()
        self.auto_running = False
        self.selected_pid: int | None = None
        self.last_log_len = 0
        self._color_cache: dict[int, str] = {}

        self._build_layout()
        self._render_snapshot()

    def _build_layout(self) -> None:
        control = ttk.Frame(self.root)
        control.pack(fill=tk.X, padx=8, pady=4)

        ttk.Button(control, text="单步执行", command=self._on_step).pack(side=tk.LEFT, padx=4)
        self.auto_btn = ttk.Button(control, text="自动运行", command=self._toggle_auto)
        self.auto_btn.pack(side=tk.LEFT, padx=4)
        ttk.Button(control, text="重置", command=self._on_reset).pack(side=tk.LEFT, padx=4)
        self.clock_label = ttk.Label(control, text="时钟: 0")
        self.clock_label.pack(side=tk.RIGHT)

        body = ttk.Frame(self.root)
        body.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(body)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4, pady=4)
        right = ttk.Frame(body)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=4, pady=4)

        self.process_tree = ttk.Treeview(
            left,
            columns=("proc", "state", "remain", "quantum", "queue"),
            show="headings",
            height=8,
        )
        self.process_tree.heading("proc", text="进程")
        self.process_tree.heading("state", text="状态")
        self.process_tree.heading("remain", text="剩余动作")
        self.process_tree.heading("quantum", text="时间片")
        self.process_tree.heading("queue", text="队列")
        self.process_tree.column("proc", width=130)
        self.process_tree.column("state", width=80)
        self.process_tree.column("remain", width=80)
        self.process_tree.column("quantum", width=80)
        self.process_tree.column("queue", width=60)
        ttk.Label(left, text="进程管理 / 调度").pack(anchor=tk.W)
        self.process_tree.pack(fill=tk.BOTH, expand=True)
        self.process_tree.bind("<<TreeviewSelect>>", self._on_select_process)

        queue_frame = ttk.LabelFrame(left, text="多级反馈队列 (Q0/Q1/Q2)")
        queue_frame.pack(fill=tk.X, pady=(4, 4))
        self.queue_boxes = []
        for idx in range(3):
            sub = ttk.Frame(queue_frame)
            sub.pack(fill=tk.X, pady=2)
            ttk.Label(sub, text=f"Q{idx}").pack(side=tk.LEFT)
            box = tk.Listbox(sub, height=2, exportselection=False)
            box.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
            self.queue_boxes.append(box)

        mem_frame = ttk.LabelFrame(left, text="存储 / 虚拟内存")
        mem_frame.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

        self.memory_info = ttk.Label(mem_frame, text="物理帧: 0 已用: 0 空闲: 0")
        self.memory_info.pack(anchor=tk.W, padx=4, pady=(4, 0))

        canvas_wrap = ttk.Frame(mem_frame)
        canvas_wrap.pack(fill=tk.BOTH, expand=True, padx=4)
        self.memory_canvas = tk.Canvas(canvas_wrap, height=220, background="#f7f7f7")
        self.memory_canvas.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)

        side_bar = ttk.Frame(canvas_wrap)
        side_bar.pack(side=tk.RIGHT, fill=tk.Y, padx=(6, 0))
        ttk.Label(side_bar, text="空闲帧").pack(anchor=tk.W)
        self.free_list = tk.Listbox(side_bar, height=6)
        self.free_list.pack(fill=tk.X, pady=(0, 6))

        ttk.Label(side_bar, text="页表 (点击进程显示)").pack(anchor=tk.W)
        self.page_table_tree = ttk.Treeview(
            side_bar, columns=("page", "frame", "status"), show="headings", height=8
        )
        self.page_table_tree.heading("page", text="页号")
        self.page_table_tree.heading("frame", text="帧号")
        self.page_table_tree.heading("status", text="状态")
        self.page_table_tree.column("page", width=50, anchor=tk.CENTER)
        self.page_table_tree.column("frame", width=60, anchor=tk.CENTER)
        self.page_table_tree.column("status", width=90, anchor=tk.W)
        self.page_table_tree.pack(fill=tk.BOTH, expand=True)

        ttk.Label(right, text="文件管理").pack(anchor=tk.W)
        self.file_tree = ttk.Treeview(right, columns=("owner", "size"), show="headings", height=6)
        self.file_tree.heading("owner", text="所属进程")
        self.file_tree.heading("size", text="大小(KB)")
        self.file_tree.column("owner", width=90)
        self.file_tree.column("size", width=90)
        self.file_tree.pack(fill=tk.X, padx=2, pady=(0, 8))

        buffer_frame = ttk.LabelFrame(right, text="生产者-消费者缓冲池")
        buffer_frame.pack(fill=tk.X, padx=2, pady=(0, 8))
        ttk.Label(buffer_frame, text="生产者").pack(anchor=tk.W, padx=6, pady=(2, 0))
        self.buffer_status = ttk.Label(buffer_frame, text="缓冲区: 0/0")
        self.buffer_status.pack(anchor=tk.W, padx=6)
        self.buffer_canvas = tk.Canvas(buffer_frame, height=120, background="#fafafa")
        self.buffer_canvas.pack(fill=tk.X, padx=6, pady=4)
        ttk.Label(buffer_frame, text="消费者").pack(anchor=tk.W, padx=6, pady=(0, 4))

        ttk.Label(right, text="事件日志 (动态过程)").pack(anchor=tk.W)
        self.log_area = scrolledtext.ScrolledText(right, height=18, state=tk.DISABLED)
        self.log_area.pack(fill=tk.BOTH, expand=True)

    def _clear_tree(self, tree: ttk.Treeview) -> None:
        for item in tree.get_children():
            tree.delete(item)

    def _color_for_pid(self, pid: int) -> str:
        if pid not in self._color_cache:
            palette = [
                "#c7e9c0",
                "#a1d99b",
                "#74c476",
                "#31a354",
                "#add8e6",
                "#9ecae1",
                "#6baed6",
                "#4292c6",
                "#fdd0a2",
                "#fdae6b",
                "#fd8d3c",
                "#e6550d",
            ]
            self._color_cache[pid] = palette[len(self._color_cache) % len(palette)]
        return self._color_cache[pid]

    def _render_processes(self, snapshot: dict) -> None:
        self._clear_tree(self.process_tree)
        rows = []
        if snapshot["running"]:
            proc = snapshot["running"]
            rows.append(
                (
                    f"{proc.pid}-{proc.name}",
                    proc.state,
                    proc.remaining_actions,
                    proc.current_quantum,
                    f"Q{proc.queue_level}",
                )
            )
        for level, queue in enumerate(snapshot["ready"]):
            for proc in queue:
                rows.append(
                    (
                        f"{proc.pid}-{proc.name}",
                        proc.state,
                        proc.remaining_actions,
                        proc.current_quantum,
                        f"Q{level}",
                    )
                )
        for proc in snapshot["blocked"]:
            detail = proc.wait_reason or f"阻塞({proc.io_timer})"
            rows.append(
                (
                    f"{proc.pid}-{proc.name}",
                    detail,
                    proc.remaining_actions,
                    proc.current_quantum,
                    f"Q{proc.queue_level}",
                )
            )
        for proc in snapshot["finished"]:
            rows.append(
                (
                    f"{proc.pid}-{proc.name}",
                    proc.state,
                    proc.remaining_actions,
                    proc.current_quantum,
                    f"Q{proc.queue_level}",
                )
            )

        for name, state, remain, quantum, level in rows:
            self.process_tree.insert("", tk.END, values=(name, state, remain, quantum, level))

    def _render_queues(self, snapshot: dict) -> None:
        for idx, box in enumerate(self.queue_boxes):
            box.delete(0, tk.END)
            for proc in snapshot["ready"][idx]:
                box.insert(tk.END, f"P{proc.pid}({proc.current_quantum})")

    def _render_memory(self, snapshot: dict) -> None:
        frames = snapshot["frames"]
        used = len([f for f in frames if f is not None])
        free = len(frames) - used
        self.memory_info.configure(text=f"物理帧: {len(frames)} 已用: {used} 空闲: {free}")

        # Draw memory grid similar to textbook paging diagrams.
        self.memory_canvas.delete("all")
        cols = max(4, math.ceil(math.sqrt(len(frames))))
        cell_w, cell_h = 90, 42
        pad = 6
        for idx, cell in enumerate(frames):
            row, col = divmod(idx, cols)
            x1, y1 = col * (cell_w + pad), row * (cell_h + pad)
            x2, y2 = x1 + cell_w, y1 + cell_h
            fill = "#f1f1f1" if cell is None else self._color_for_pid(cell[0])
            outline_width = 3 if snapshot["last_access"] == idx else 1
            self.memory_canvas.create_rectangle(x1, y1, x2, y2, fill=fill, outline="#555", width=outline_width)
            label = "空闲" if cell is None else f"P{cell[0]}.{cell[1]}"
            self.memory_canvas.create_text((x1 + x2) / 2, (y1 + y2) / 2, text=label)
            self.memory_canvas.create_text(x1 + 14, y1 + 12, text=str(idx), font=("TkDefaultFont", 8), fill="#333")

        total_rows = math.ceil(len(frames) / cols)
        self.memory_canvas.configure(scrollregion=(0, 0, cols * (cell_w + pad), total_rows * (cell_h + pad)))

        self.free_list.delete(0, tk.END)
        for idx, cell in enumerate(frames):
            if cell is None:
                self.free_list.insert(tk.END, idx)

        self._render_page_table(snapshot)

    def _render_files(self, snapshot: dict) -> None:
        self._clear_tree(self.file_tree)
        for path, entry in snapshot["files"].items():
            self.file_tree.insert("", tk.END, text=path, values=(entry.owner, entry.size))

    def _render_buffer(self, snapshot: dict) -> None:
        buf = snapshot["buffer"]
        capacity = buf["capacity"]
        slots = buf["slots"]
        used = buf["used"]
        in_ptr = buf["in"]
        out_ptr = buf["out"]
        self.buffer_status.configure(text=f"缓冲区: {used}/{capacity}")

        self.buffer_canvas.delete("all")
        margin = 20
        cell_w = 70
        cell_h = 40
        gap = 6
        for idx in range(capacity):
            x1 = margin + idx * (cell_w + gap)
            y1 = 20
            x2 = x1 + cell_w
            y2 = y1 + cell_h
            owner = slots[idx]
            fill = "#fff" if owner is None else self._color_for_pid(owner)
            self.buffer_canvas.create_rectangle(
                x1, y1, x2, y2, fill=fill, outline="#555", width=2
            )
            label = f"P{owner}" if owner is not None else ""
            self.buffer_canvas.create_text((x1 + x2) / 2, (y1 + y2) / 2, text=label)
            self.buffer_canvas.create_text((x1 + x2) / 2, y1 - 10, text=str(idx))

        def draw_arrow(position: int, color: str, text: str, dy: int) -> None:
            x1 = margin + position * (cell_w + gap)
            x2 = x1 + cell_w
            mid_x = (x1 + x2) / 2
            base_y = 20 + cell_h + dy
            self.buffer_canvas.create_line(mid_x, base_y, mid_x, base_y - dy + 6, arrow=tk.LAST, fill=color, width=2)
            self.buffer_canvas.create_text(mid_x, base_y + (8 if dy > 0 else -12), text=text, fill=color)

        draw_arrow(in_ptr, "#d62728", "in", -20)
        draw_arrow(out_ptr, "#1f77b4", "out", 34)

    def _render_logs(self, snapshot: dict) -> None:
        self.log_area.configure(state=tk.NORMAL)
        for line in snapshot["log"][self.last_log_len :]:
            self.log_area.insert(tk.END, line + "\n")
        self.last_log_len = len(snapshot["log"])
        self.log_area.configure(state=tk.DISABLED)
        self.log_area.yview_moveto(1.0)

    def _render_page_table(self, snapshot: dict) -> None:
        self._clear_tree(self.page_table_tree)
        pid = self.selected_pid
        if pid is None and snapshot["running"]:
            pid = snapshot["running"].pid
        if pid is None:
            return
        table = snapshot["page_tables"].get(pid, {})
        meta = snapshot.get("process_meta", {}).get(pid)
        total_pages = meta.get("memory_pages") if meta else None
        pages = range(total_pages) if total_pages is not None else sorted(table.keys())
        for page in pages:
            frame = table.get(page)
            status = "驻留" if frame is not None else "未装入"
            frame_text = frame if frame is not None else "-"
            self.page_table_tree.insert("", tk.END, values=(page, frame_text, status))

    def _render_snapshot(self) -> None:
        snapshot = self.simulator.snapshot()
        self.clock_label.configure(text=f"时钟: {snapshot['clock']}")
        self._render_processes(snapshot)
        self._render_queues(snapshot)
        self._render_memory(snapshot)
        self._render_files(snapshot)
        self._render_buffer(snapshot)
        self._render_logs(snapshot)

    def _run_loop(self) -> None:
        if not self.auto_running:
            return
        self._on_step()
        self.root.after(800, self._run_loop)

    def _on_step(self) -> None:
        self.simulator.step()
        self._render_snapshot()

    def _toggle_auto(self) -> None:
        self.auto_running = not self.auto_running
        self.auto_btn.configure(text="暂停" if self.auto_running else "自动运行")
        if self.auto_running:
            self._run_loop()

    def _on_reset(self) -> None:
        self.simulator.reset()
        self.auto_running = False
        self.auto_btn.configure(text="自动运行")
        self.selected_pid = None
        self.last_log_len = 0
        self._render_snapshot()

    def _on_select_process(self, event: tk.Event) -> None:
        selection = self.process_tree.selection()
        if not selection:
            return
        item = selection[0]
        values = self.process_tree.item(item, "values")
        if not values:
            return
        name = values[0]
        try:
            self.selected_pid = int(name.split("-")[0])
        except ValueError:
            self.selected_pid = None
        self._render_snapshot()


def main() -> None:
    root = tk.Tk()
    root.geometry("960x640")
    SimulatorGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
