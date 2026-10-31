#!/usr/bin/env python3
"""SOBOSUBA 修改器启动器（中文 GUI）。

功能：
  - 启动内置修改器版 / 原版
  - 游戏更新后一键重新生成修改器版
  - 备份 / 恢复游戏存档
  - 查看使用说明和控制台命令
"""

import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).resolve().parent
    RES_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))
else:
    APP_DIR = Path(__file__).resolve().parent
    RES_DIR = APP_DIR
    tools_dir = APP_DIR / "tools"
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))

import build_cheat

CHEAT_SOURCE = RES_DIR / "cheat.gd"
if getattr(sys, "frozen", False):
    ICON_PNG = RES_DIR / "sobosuba_mod_small.png"
    ICON_ICO = RES_DIR / "sobosuba_mod.ico"
else:
    ICON_PNG = APP_DIR / "icons" / "sobosuba_mod_small.png"
    ICON_ICO = APP_DIR / "icons" / "sobosuba_mod.ico"
BACKUP_DIR = APP_DIR / "backups"
USER_DATA = Path(os.environ.get("APPDATA", "")) / "Godot" / "app_userdata" / "sobosuba"

GAME_CANDIDATES = [
    Path(r"E:\SteamLibrary\steamapps\common\sobosuba"),
    Path(r"D:\game\ABS\sobosuba"),
    Path(r"C:\SteamLibrary\steamapps\common\sobosuba"),
]

SAVE_ITEMS = [
    "achievements.dat",
    "style_unlocks.dat",
    "settings.tres",
    "game_state.tres",
    "styles",
]

COLORS = {
    "bg": "#0b1016",
    "panel": "#121a24",
    "panel2": "#182430",
    "accent": "#35c9dc",
    "accent_dark": "#1d7f8c",
    "text": "#e8f4f8",
    "muted": "#8aa3b0",
    "ok": "#6ee7a8",
    "warn": "#f2c14e",
    "error": "#ff7b72",
}

HELP_TEXT = """使用步骤
1. 点击「启动修改器版」。
2. 进入游戏后按 F2 打开修改器菜单。
3. 把鼠标放到球场上，按 F3 在鼠标位置生成当前等级的球。
4. 按 F1 或 F4 打开开发者控制台。

修改器菜单功能
· 分数：直接设置、+1000、+10000（会同步刷新分数显示）
· 速度：0.25x～4x 时间倍率（慢动作 / 加速）
· 玩法：关闭重力、冻结危险挡板、关闭合并、冻结所有球、结束本局
· 解锁：全部样式 / 成就 / 生成档位；本地排行榜加分或清空
· 球：按 F3 生成指定等级球、清空所有球、修复球形状
· 存档：保存 / 读取 / 删除当前进度
· 控制台：一键打开开发者控制台

控制台常用命令
cheat_unlock_all             解锁全部样式、成就和生成档位
cheat_score_set 10000        设置当前分数
cheat_score_add 1000         当前分数增加
cheat_time 0.5               时间倍率（0.5 = 慢动作）
cheat_spawn 8                在鼠标位置生成 8 级球
cheat_clear_sobos            清空所有球
cheat_gravity 0              关闭重力
cheat_freeze_bumpers true    冻结危险挡板
cheat_merging false          关闭合并
cheat_game_over              结束本局
unlock_all_styles            解锁全部样式（游戏自带命令）
unlock_all_achievements      解锁全部成就（游戏自带命令）
add_local_score 999999       本地排行榜添加分数
clear_saved_game             删除当前局存档

注意事项
· 仅限单人游戏娱乐使用。
· 原版 sobosuba.exe 不会被修改；修改器版是独立的 sobosuba.cheat.exe。
· 游戏更新后，点击「重新生成修改器版」即可基于新版重新注入。
· 修改存档前建议先点「备份存档」；「恢复存档」可随时还原。
"""


def find_default_game_dir() -> Path | None:
    for candidate in GAME_CANDIDATES:
        if (candidate / "sobosuba.exe").is_file():
            return candidate
    return None


def is_game_running() -> bool:
    """通过 tasklist 粗略判断游戏是否在运行。"""
    try:
        result = subprocess.run(
            ["tasklist"], capture_output=True, text=True, errors="ignore", timeout=10
        )
        text = (result.stdout or "").lower()
        return "sobosuba.cheat.exe" in text or "sobosuba.exe" in text
    except Exception:
        return False


class TrainerGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("SOBOSUBA 修改器启动器")
        self.root.geometry("980x700")
        self.root.minsize(880, 620)
        self.root.configure(bg=COLORS["bg"])
        self.game_dir_var = tk.StringVar()
        self.status_var = tk.StringVar(value="就绪")
        self._child_process: subprocess.Popen | None = None
        self._build_in_progress = False
        self._ui_queue: queue.Queue = queue.Queue()

        self._setup_style()
        self._build_ui()
        default_dir = find_default_game_dir()
        if default_dir:
            self.game_dir_var.set(str(default_dir))
        self._refresh_status()
        self.root.after(150, self._drain_ui_queue)

    # ------------------------------------------------------------
    # 界面
    # ------------------------------------------------------------
    def _setup_style(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", background=COLORS["bg"], foreground=COLORS["text"])
        style.configure("TFrame", background=COLORS["bg"])
        style.configure("Panel.TFrame", background=COLORS["panel"])
        style.configure(
            "TLabel", background=COLORS["bg"], foreground=COLORS["text"],
            font=("Microsoft YaHei UI", 10)
        )
        style.configure(
            "Title.TLabel", font=("Microsoft YaHei UI", 20, "bold"),
            foreground=COLORS["accent"], background=COLORS["bg"]
        )
        style.configure(
            "Sub.TLabel", foreground=COLORS["muted"], background=COLORS["bg"],
            font=("Microsoft YaHei UI", 9)
        )
        style.configure(
            "Status.TLabel", foreground=COLORS["ok"], background=COLORS["bg"],
            font=("Microsoft YaHei UI", 9)
        )
        style.configure(
            "TButton", font=("Microsoft YaHei UI", 10), padding=(12, 7),
            background=COLORS["panel2"], foreground=COLORS["text"],
            bordercolor=COLORS["panel2"], lightcolor=COLORS["panel2"],
            darkcolor=COLORS["panel2"]
        )
        style.map(
            "TButton",
            background=[("active", "#223243"), ("disabled", "#1a222a")],
            foreground=[("disabled", COLORS["muted"])],
        )
        style.configure(
            "Accent.TButton", font=("Microsoft YaHei UI", 11, "bold"),
            background=COLORS["accent"], foreground="#04222a",
            bordercolor=COLORS["accent"], lightcolor=COLORS["accent"],
            darkcolor=COLORS["accent_dark"], padding=(14, 10)
        )
        style.map(
            "Accent.TButton",
            background=[("active", "#5fe3f2"), ("disabled", "#1d4c54")],
            foreground=[("disabled", "#0b1016")],
        )
        style.configure(
            "TEntry", fieldbackground=COLORS["panel2"], foreground=COLORS["text"],
            insertcolor=COLORS["text"], bordercolor=COLORS["panel2"],
            padding=6
        )
        style.configure("TNotebook", background=COLORS["bg"], borderwidth=0)
        style.configure(
            "TNotebook.Tab", background=COLORS["panel"], foreground=COLORS["muted"],
            padding=(16, 7), font=("Microsoft YaHei UI", 10)
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", COLORS["panel2"])],
            foreground=[("selected", COLORS["accent"])],
        )

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=18)
        outer.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(outer)
        header.pack(fill=tk.X)
        ttk.Label(header, text="SOBOSUBA 修改器", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(
            header,
            text="内置中文作弊菜单 · F2 开关 · 原版文件不会被修改",
            style="Sub.TLabel",
        ).pack(anchor=tk.W, pady=(2, 12))

        path_frame = ttk.Frame(outer)
        path_frame.pack(fill=tk.X, pady=(0, 12))
        ttk.Label(path_frame, text="游戏目录").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Entry(path_frame, textvariable=self.game_dir_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        ttk.Button(path_frame, text="浏览…", command=self._browse).pack(
            side=tk.LEFT, padx=(8, 0)
        )

        button_frame = ttk.Frame(outer)
        button_frame.pack(fill=tk.X, pady=(0, 10))
        self.launch_cheat_btn = ttk.Button(
            button_frame, text="启动修改器版", style="Accent.TButton",
            command=self._launch_cheat
        )
        self.launch_cheat_btn.pack(side=tk.LEFT)
        ttk.Button(button_frame, text="启动原版", command=self._launch_original).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        self.rebuild_btn = ttk.Button(
            button_frame, text="重新生成修改器版", command=self._rebuild_cheat
        )
        self.rebuild_btn.pack(side=tk.LEFT, padx=(8, 0))

        button_frame2 = ttk.Frame(outer)
        button_frame2.pack(fill=tk.X, pady=(0, 10))
        ttk.Button(button_frame2, text="备份存档", command=self._backup_save).pack(
            side=tk.LEFT
        )
        ttk.Button(button_frame2, text="恢复存档…", command=self._restore_save).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        ttk.Button(button_frame2, text="打开存档目录", command=self._open_user_dir).pack(
            side=tk.LEFT, padx=(8, 0)
        )

        ttk.Label(outer, textvariable=self.status_var, style="Status.TLabel").pack(
            anchor=tk.W, pady=(0, 8)
        )

        notebook = ttk.Notebook(outer)
        notebook.pack(fill=tk.BOTH, expand=True)

        help_frame = ttk.Frame(notebook, padding=10)
        notebook.add(help_frame, text="使用说明")
        help_text = scrolledtext.ScrolledText(
            help_frame, wrap=tk.WORD, font=("Microsoft YaHei UI", 10),
            bg=COLORS["panel"], fg=COLORS["text"], insertbackground=COLORS["text"],
            relief=tk.FLAT, padx=12, pady=12
        )
        help_text.pack(fill=tk.BOTH, expand=True)
        help_text.insert("1.0", HELP_TEXT)
        help_text.configure(state=tk.DISABLED)

        log_frame = ttk.Frame(notebook, padding=10)
        notebook.add(log_frame, text="运行日志")
        self.log_text = scrolledtext.ScrolledText(
            log_frame, wrap=tk.WORD, font=("Consolas", 10),
            bg=COLORS["panel"], fg=COLORS["text"], insertbackground=COLORS["text"],
            relief=tk.FLAT, padx=12, pady=12
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.configure(state=tk.DISABLED)

        ttk.Label(
            outer,
            text="仅限单人游戏娱乐使用 · 修改器版 sobosuba.cheat.exe 与原版共存",
            style="Sub.TLabel",
        ).pack(anchor=tk.W, pady=(8, 0))

    # ------------------------------------------------------------
    # 路径与状态
    # ------------------------------------------------------------
    def _game_dir(self) -> Path | None:
        value = self.game_dir_var.get().strip().strip('"')
        if not value:
            return None
        path = Path(value)
        if path.is_file():
            path = path.parent
        return path if path.is_dir() else None

    def _original_exe(self) -> Path | None:
        game_dir = self._game_dir()
        if not game_dir:
            return None
        return game_dir / "sobosuba.exe"

    def _cheat_exe(self) -> Path | None:
        game_dir = self._game_dir()
        if not game_dir:
            return None
        return game_dir / "sobosuba.cheat.exe"

    def _refresh_status(self) -> None:
        game_dir = self._game_dir()
        if not game_dir:
            self.status_var.set("未找到游戏目录，请点击「浏览…」选择 sobosuba.exe")
            return
        original = game_dir / "sobosuba.exe"
        cheat = game_dir / "sobosuba.cheat.exe"
        parts = []
        parts.append(f"原版：{'已找到' if original.is_file() else '缺失'}")
        parts.append(f"修改器版：{'已生成' if cheat.is_file() else '未生成'}")
        if is_game_running():
            parts.append("游戏正在运行")
        self.status_var.set(" · ".join(parts))

    def _browse(self) -> None:
        current = self._game_dir()
        initial = str(current) if current else ""
        selected = filedialog.askopenfilename(
            title="选择 sobosuba.exe",
            initialdir=initial,
            filetypes=[("sobosuba", "sobosuba*.exe"), ("可执行文件", "*.exe")],
        )
        if selected:
            self.game_dir_var.set(str(Path(selected).parent))
            self._refresh_status()

    # ------------------------------------------------------------
    # 启动游戏
    # ------------------------------------------------------------
    def _launch(self, exe: Path | None, label: str) -> None:
        if exe is None:
            messagebox.showerror("路径错误", "请先选择正确的游戏目录。")
            return
        if not exe.is_file():
            messagebox.showerror("文件缺失", f"找不到 {exe.name}。\n请检查游戏目录。")
            return
        if is_game_running():
            if not messagebox.askyesno(
                "游戏正在运行",
                "检测到 sobosuba 已经在运行。\n"
                "同时启动两个实例可能导致存档冲突。\n\n仍要继续吗？",
            ):
                return
        try:
            process = subprocess.Popen([str(exe)], cwd=str(exe.parent))
        except Exception as exc:
            messagebox.showerror("启动失败", f"无法启动游戏：\n{exc}")
            return
        self._child_process = process
        self._log(f"已启动{label}：{exe}")
        self.status_var.set(f"已启动{label}，按 F2 打开修改器菜单")
        self.root.iconify()
        self.root.after(1000, self._poll_child_process)

    def _poll_child_process(self) -> None:
        if self._child_process is None:
            return
        if self._child_process.poll() is None:
            self.root.after(1000, self._poll_child_process)
            return
        self._child_process = None
        try:
            self.root.deiconify()
        except tk.TclError:
            pass
        self._log("游戏已退出")
        self._refresh_status()

    def _launch_cheat(self) -> None:
        self._refresh_status()
        cheat = self._cheat_exe()
        if cheat is None or not cheat.is_file():
            if messagebox.askyesno(
                "尚未生成修改器版",
                "还没有找到 sobosuba.cheat.exe。\n是否现在根据原版生成？",
            ):
                self._rebuild_cheat()
            return
        self._launch(cheat, "修改器版")

    def _launch_original(self) -> None:
        self._launch(self._original_exe(), "原版")

    # ------------------------------------------------------------
    # 重新生成修改器版
    # ------------------------------------------------------------
    def _rebuild_cheat(self) -> None:
        if self._build_in_progress:
            return
        original = self._original_exe()
        cheat = self._cheat_exe()
        if original is None or not original.is_file():
            messagebox.showerror("路径错误", "找不到原版 sobosuba.exe。")
            return
        if is_game_running():
            messagebox.showwarning(
                "游戏正在运行", "请先关闭游戏（包括修改器版），再重新生成，否则文件会被占用。"
            )
            return
        if not messagebox.askyesno(
            "重新生成修改器版",
            "将从原版 exe 重新生成 sobosuba.cheat.exe。\n"
            "原版文件不会被修改。\n\n继续吗？",
        ):
            return
        self._build_in_progress = True
        self.rebuild_btn.configure(state=tk.DISABLED)
        self.status_var.set("正在生成修改器版，请稍候…")
        self._log("开始重新生成修改器版…")
        threading.Thread(
            target=self._run_rebuild, args=(original, cheat), daemon=True
        ).start()

    def _run_rebuild(self, original: Path, cheat: Path) -> None:
        try:
            self._log("正在从原版 exe 生成修改器版…")
            result = build_cheat.build(
                str(original), str(cheat), str(CHEAT_SOURCE),
                icon_png=str(ICON_PNG),
            )
            self._log(
                f"生成成功：{result['out_exe']}（{result['out_size']} 字节，"
                f"{result['pck_files']} 个文件）"
            )
            self._ui_queue.put(("rebuild_done", True))
        except Exception as exc:
            self._log(f"生成异常：{exc}")
            self._ui_queue.put(("rebuild_done", False))

    def _on_rebuild_success(self) -> None:
        self._build_in_progress = False
        self.rebuild_btn.configure(state=tk.NORMAL)
        self.status_var.set("修改器版生成成功")
        self._refresh_status()

    def _on_rebuild_failed(self) -> None:
        self._build_in_progress = False
        self.rebuild_btn.configure(state=tk.NORMAL)
        self.status_var.set("生成失败，请查看运行日志")
        messagebox.showerror("生成失败", "请确保游戏已关闭，并查看「运行日志」中的详细信息。")

    # ------------------------------------------------------------
    # 存档备份 / 恢复
    # ------------------------------------------------------------
    def _backup_save(self) -> None:
        if not USER_DATA.is_dir():
            messagebox.showerror("找不到存档", f"存档目录不存在：\n{USER_DATA}")
            return
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = BACKUP_DIR / f"sobosuba_{stamp}"
        try:
            target.mkdir(parents=True, exist_ok=True)
            for item in SAVE_ITEMS:
                source = USER_DATA / item
                if not source.exists():
                    continue
                if source.is_dir():
                    shutil.copytree(source, target / item, dirs_exist_ok=True)
                else:
                    shutil.copy2(source, target / item)
        except Exception as exc:
            messagebox.showerror("备份失败", str(exc))
            return
        self._log(f"存档已备份：{target}")
        self.status_var.set("存档备份完成")
        messagebox.showinfo("备份完成", f"存档已备份到：\n{target}")

    def _restore_save(self) -> None:
        if is_game_running():
            messagebox.showwarning(
                "游戏正在运行", "请先关闭游戏再恢复存档，否则退出时可能覆盖恢复结果。"
            )
            return
        if not USER_DATA.is_dir():
            messagebox.showerror("找不到存档", f"存档目录不存在：\n{USER_DATA}")
            return
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        selected = filedialog.askdirectory(
            title="选择要恢复的备份目录", initialdir=str(BACKUP_DIR)
        )
        if not selected:
            return
        backup_path = Path(selected)
        if not messagebox.askyesno(
            "确认恢复存档",
            f"将用以下备份覆盖当前存档：\n{backup_path}\n\n继续吗？",
        ):
            return
        try:
            for item in SAVE_ITEMS:
                source = backup_path / item
                if not source.exists():
                    continue
                target = USER_DATA / item
                if source.is_dir():
                    shutil.copytree(source, target, dirs_exist_ok=True)
                else:
                    shutil.copy2(source, target)
        except Exception as exc:
            messagebox.showerror("恢复失败", str(exc))
            return
        self._log(f"存档已恢复：{backup_path}")
        self.status_var.set("存档恢复完成")
        messagebox.showinfo("恢复完成", "存档已恢复。请重新启动游戏。")

    def _open_user_dir(self) -> None:
        if not USER_DATA.is_dir():
            messagebox.showerror("找不到存档", f"存档目录不存在：\n{USER_DATA}")
            return
        os.startfile(str(USER_DATA))

    # ------------------------------------------------------------
    # 日志
    # ------------------------------------------------------------
    def _log(self, message: str) -> None:
        if not message:
            return
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._ui_queue.put(("log", f"[{timestamp}] {message}\n"))

    def _drain_ui_queue(self) -> None:
        try:
            while True:
                kind, payload = self._ui_queue.get_nowait()
                if kind == "log":
                    self._append_log_text(payload)
                elif kind == "rebuild_done":
                    if payload:
                        self._on_rebuild_success()
                    else:
                        self._on_rebuild_failed()
        except queue.Empty:
            pass
        try:
            self.root.after(150, self._drain_ui_queue)
        except tk.TclError:
            pass

    def _append_log_text(self, text: str) -> None:
        try:
            self.log_text.configure(state=tk.NORMAL)
            self.log_text.insert(tk.END, text)
            self.log_text.see(tk.END)
            self.log_text.configure(state=tk.DISABLED)
        except tk.TclError:
            pass


def cli_rebuild(game_dir: str) -> int:
    """命令行重建：python trainer_gui.py --rebuild <游戏目录>"""
    game_path = Path(game_dir)
    original = game_path / "sobosuba.exe"
    cheat = game_path / "sobosuba.cheat.exe"
    if not original.is_file():
        print(f"找不到原版 exe：{original}")
        return 1
    try:
        result = build_cheat.build(
                str(original), str(cheat), str(CHEAT_SOURCE),
                icon_png=str(ICON_PNG),
            )
        print(
            f"生成成功：{result['out_exe']}（{result['out_size']} 字节，"
            f"{result['pck_files']} 个文件）"
        )
        return 0
    except Exception as exc:
        print(f"生成失败：{exc}")
        return 1


def main() -> None:
    root = tk.Tk()
    if ICON_ICO.is_file():
        try:
            root.iconbitmap(default=str(ICON_ICO))
        except Exception:
            pass
    if ICON_PNG.is_file():
        try:
            root._icon_photo = tk.PhotoImage(file=str(ICON_PNG))
            root.iconphoto(True, root._icon_photo)
        except Exception:
            pass
    TrainerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--rebuild":
        sys.exit(cli_rebuild(sys.argv[2]))
    main()
