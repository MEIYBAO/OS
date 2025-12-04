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
            left, columns=("proc", "state", "remain", "quantum"), show="headings", height=8
        )
        self.process_tree.heading("proc", text="进程")
        self.process_tree.heading("state", text="状态")
        self.process_tree.heading("remain", text="剩余动作")
        self.process_tree.heading("quantum", text="时间片")
        self.process_tree.column("proc", width=130)
        self.process_tree.column("state", width=80)
        self.process_tree.column("remain", width=80)
        self.process_tree.column("quantum", width=80)
        ttk.Label(left, text="进程管理 / 调度").pack(anchor=tk.W)
        self.process_tree.pack(fill=tk.BOTH, expand=True)

        self.memory_tree = ttk.Treeview(left, columns=("frame", "page"), show="headings", height=8)
        self.memory_tree.heading("frame", text="物理帧")
        self.memory_tree.heading("page", text="占用(进程,页)")
        self.memory_tree.column("frame", width=80)
        self.memory_tree.column("page", width=160)
        ttk.Label(left, text="存储 / 虚拟内存").pack(anchor=tk.W, pady=(8, 0))
        self.memory_tree.pack(fill=tk.BOTH, expand=True)

        ttk.Label(right, text="文件管理").pack(anchor=tk.W)
        self.file_tree = ttk.Treeview(right, columns=("owner", "size"), show="headings", height=6)
        self.file_tree.heading("owner", text="所属进程")
        self.file_tree.heading("size", text="大小(KB)")
        self.file_tree.column("owner", width=90)
        self.file_tree.column("size", width=90)
        self.file_tree.pack(fill=tk.X, padx=2, pady=(0, 8))

        ttk.Label(right, text="事件日志 (动态过程)").pack(anchor=tk.W)
        self.log_area = scrolledtext.ScrolledText(right, height=18, state=tk.DISABLED)
        self.log_area.pack(fill=tk.BOTH, expand=True)

    def _clear_tree(self, tree: ttk.Treeview) -> None:
        for item in tree.get_children():
            tree.delete(item)

    def _render_processes(self, snapshot: dict) -> None:
        self._clear_tree(self.process_tree)
        rows = []
        if snapshot["running"]:
            proc = snapshot["running"]
            rows.append((f"{proc.pid}-{proc.name}", proc.state, proc.remaining_actions, proc.current_quantum))
        for proc in snapshot["ready"]:
            rows.append((f"{proc.pid}-{proc.name}", proc.state, proc.remaining_actions, proc.current_quantum))
        for proc in snapshot["blocked"]:
            rows.append((f"{proc.pid}-{proc.name}", f"{proc.state}({proc.io_timer})", proc.remaining_actions, proc.current_quantum))
        for proc in snapshot["finished"]:
            rows.append((f"{proc.pid}-{proc.name}", proc.state, proc.remaining_actions, proc.current_quantum))

        for name, state, remain, quantum in rows:
            self.process_tree.insert("", tk.END, values=(name, state, remain, quantum))

    def _render_memory(self, snapshot: dict) -> None:
        self._clear_tree(self.memory_tree)
        for idx, cell in enumerate(snapshot["frames"]):
            label = "空闲" if cell is None else f"P{cell[0]} 页{cell[1]}"
            self.memory_tree.insert("", tk.END, values=(idx, label))
        if snapshot["last_access"] is not None:
            children = self.memory_tree.get_children()
            if 0 <= snapshot["last_access"] < len(children):
                self.memory_tree.selection_set(children[snapshot["last_access"]])

    def _render_files(self, snapshot: dict) -> None:
        self._clear_tree(self.file_tree)
        for path, entry in snapshot["files"].items():
            self.file_tree.insert("", tk.END, text=path, values=(entry.owner, entry.size))

    def _render_logs(self, snapshot: dict) -> None:
        self.log_area.configure(state=tk.NORMAL)
        self.log_area.delete(1.0, tk.END)
        for line in snapshot["log"]:
            self.log_area.insert(tk.END, line + "\n")
        self.log_area.configure(state=tk.DISABLED)
        self.log_area.yview_moveto(1.0)

    def _render_snapshot(self) -> None:
        snapshot = self.simulator.snapshot()
        self.clock_label.configure(text=f"时钟: {snapshot['clock']}")
        self._render_processes(snapshot)
        self._render_memory(snapshot)
        self._render_files(snapshot)
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
        self._render_snapshot()


def main() -> None:
    root = tk.Tk()
    root.geometry("960x640")
    SimulatorGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
