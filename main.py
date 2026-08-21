"""桌面 GUI：选择上传视频，选择特效，开始处理并显示进度。

运行：
    python main.py
"""

import os
import sys
import threading
import traceback

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from effects import list_effects, DEFAULT_EFFECT
from pipeline import process_video, PipelineError

VIDEO_EXTS = (
    "*.mp4", "*.mov", "*.avi", "*.mkv", "*.webm", "*.m4v", "*.MP4", "*.MOV",
)


class App:
    def __init__(self, root):
        self.root = root
        root.title("手指取景特效 - 视频上传处理")
        root.geometry("640x340")
        root.resizable(False, False)

        self.input_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.effect_var = tk.StringVar(value=DEFAULT_EFFECT)
        self.draw_outline = tk.BooleanVar(value=False)
        self.progress = tk.DoubleVar(value=0.0)
        self.status = tk.StringVar(value="选择要处理的视频文件。")

        self._cancel = threading.Event()

        self._build_ui()

    def _build_ui(self):
        pad = {"padx": 12, "pady": 6}

        # 输入文件
        frm_in = ttk.Frame(self.root)
        frm_in.pack(fill="x", padx=12, pady=(14, 0))
        ttk.Label(frm_in, text="输入视频:").pack(side="left")
        ttk.Entry(frm_in, textvariable=self.input_path, width=52).pack(
            side="left", padx=6, fill="x", expand=True
        )
        ttk.Button(frm_in, text="浏览...", command=self._on_browse).pack(side="left")

        # 输出文件
        frm_out = ttk.Frame(self.root)
        frm_out.pack(fill="x", **pad)
        ttk.Label(frm_out, text="输出视频:").pack(side="left")
        ttk.Entry(frm_out, textvariable=self.output_path, width=52).pack(
            side="left", padx=6, fill="x", expand=True
        )
        ttk.Button(frm_out, text="保存到...", command=self._on_save).pack(side="left")

        # 特效 + 绘制框
        frm_opt = ttk.Frame(self.root)
        frm_opt.pack(fill="x", **pad)
        ttk.Label(frm_opt, text="特效:").pack(side="left")
        self.effect_combo = ttk.Combobox(
            frm_opt, textvariable=self.effect_var, state="readonly", width=30
        )
        effects = list_effects()
        self.effect_combo["values"] = [label for _, label in effects]
        self._id_to_index = {eid: i for i, (eid, _) in enumerate(effects)}
        self._index_to_id = {i: eid for i, (eid, _) in enumerate(effects)}
        self.effect_combo.current(self._id_to_index.get(DEFAULT_EFFECT, 0))
        self.effect_combo.pack(side="left", padx=6)

        ttk.Checkbutton(
            frm_opt, text="绘制取景框", variable=self.draw_outline
        ).pack(side="left", padx=12)

        # 进度条 + 状态
        ttk.Progressbar(
            self.root, variable=self.progress, maximum=1.0, length=580
        ).pack(fill="x", padx=18, pady=(16, 4))
        ttk.Label(self.root, textvariable=self.status).pack(anchor="w", padx=18)

        # 按钮
        frm_btn = ttk.Frame(self.root)
        frm_btn.pack(fill="x", padx=12, pady=16)
        self.start_btn = ttk.Button(
            frm_btn, text="开始处理", command=self._on_start
        )
        self.start_btn.pack(side="left")
        self.cancel_btn = ttk.Button(
            frm_btn, text="取消", command=self._on_cancel, state="disabled"
        )
        self.cancel_btn.pack(side="left", padx=8)
        self.open_btn = ttk.Button(
            frm_btn, text="打开输出文件", command=self._on_open, state="disabled"
        )
        self.open_btn.pack(side="left", padx=8)

    # ---- 事件 ----
    def _on_browse(self):
        path = filedialog.askopenfilename(
            title="选择视频文件",
            filetypes=[("视频文件", " ".join(VIDEO_EXTS)), ("所有文件", "*.*")],
        )
        if not path:
            return
        self.input_path.set(path)
        base, ext = os.path.splitext(path)
        out = f"{base}_processed.mp4" if ext.lower() != ".mp4" else f"{base}_processed.mp4"
        while os.path.exists(out):
            head, tail = os.path.splitext(out)
            out = f"{head}_1{tail}"
        self.output_path.set(out)

    def _on_save(self):
        path = filedialog.asksaveasfilename(
            title="保存输出视频",
            defaultextension=".mp4",
            filetypes=[("MP4 视频", "*.mp4")],
        )
        if path:
            self.output_path.set(path)

    def _on_start(self):
        if self._cancel.is_set():
            return
        in_path = self.input_path.get().strip()
        out_path = self.output_path.get().strip()

        if not in_path:
            messagebox.showwarning("提示", "请先选择输入视频文件。")
            return
        if not os.path.exists(in_path):
            messagebox.showerror("错误", "输入文件不存在。")
            return
        if not out_path:
            messagebox.showwarning("提示", "请指定输出文件路径。")
            return
        if os.path.abspath(in_path) == os.path.abspath(out_path):
            messagebox.showerror("错误", "输出文件不能与输入文件相同。")
            return

        effect_index = self.effect_combo.current()
        effect_id = self._index_to_id.get(effect_index, DEFAULT_EFFECT)
        draw = self.draw_outline.get()

        self._cancel.clear()
        self._set_processing(True)
        self.status.set("正在加载模型并处理...")
        self.progress.set(0.0)

        def work():
            try:
                def cb(fraction):
                    if fraction >= 0:
                        self.progress.set(fraction)
                        self.status.set(f"处理中 {int(fraction * 100)}%")
                    else:
                        self.status.set("处理中...")

                def cancel_check():
                    return self._cancel.is_set()

                process_video(
                    in_path,
                    out_path,
                    effect_id=effect_id,
                    draw_outline=draw,
                    progress_cb=cb,
                    cancel_check=cancel_check,
                )
                self.root.after(0, self._on_done, out_path, None)
            except PipelineError as e:
                self.root.after(0, self._on_done, None, e)
            except Exception as e:
                traceback.print_exc()
                self.root.after(0, self._on_done, None, e)

        threading.Thread(target=work, daemon=True).start()

    def _on_cancel(self):
        self._cancel.set()
        self.status.set("正在取消...")
        self.cancel_btn.config(state="disabled")

    def _on_done(self, out_path, err):
        self._set_processing(False)
        if err is not None:
            msg = str(err)
            if "已取消" in msg:
                self.status.set("已取消")
                messagebox.showinfo("信息", "处理已取消。")
            else:
                self.status.set("处理失败")
                messagebox.showerror("处理失败", msg)
            return
        self.progress.set(1.0)
        self.status.set(f"完成：{out_path}")
        self.open_btn.config(state="normal")
        messagebox.showinfo("完成", f"视频处理完成：\n{out_path}")

    def _on_open(self):
        out = self.output_path.get().strip()
        if not out or not os.path.exists(out):
            messagebox.showwarning("提示", "输出文件不存在。")
            return
        os.startfile(os.path.abspath(out))  # noqa: E999 (Windows)

    def _set_processing(self, flag):
        state = "disabled" if flag else "normal"
        self.start_btn.config(state=state)
        self.cancel_btn.config(state="normal" if flag else "disabled")
        if not flag:
            self.open_btn.config(
                state="normal"
                if self.output_path.get().strip()
                and os.path.exists(self.output_path.get().strip())
                else "disabled"
            )


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()