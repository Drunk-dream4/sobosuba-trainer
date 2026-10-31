#!/usr/bin/env python3
"""SOBOSUBA 独立修改器。

双击打开即为完整修改器界面：
  - 自动在原版游戏基础上生成一份“带修改器”的游戏副本（放在本机缓存目录，原版文件完全不动）
  - 启动副本后，通过 127.0.0.1 本地命令通道实时修改分数、速度、重力、合并、生成球等
  - 游戏内同时提供 F2 中文作弊菜单、F3 生成球、F1/F4 控制台

在其他设备上使用时，只要选择那台设备上的原版 sobosuba.exe，修改器会自动重新生成本地副本。

命令行（可选）：
  SOBOSUBA修改器.exe --selftest <sobosuba.exe>
"""

import argparse
import hashlib
import json
import os
import queue
import shutil
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

# ------------------------------------------------------------
# 路径
# ------------------------------------------------------------
if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).resolve().parent
    RES_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))
else:
    APP_DIR = Path(__file__).resolve().parent
    RES_DIR = APP_DIR
    if not (RES_DIR / "cheat.gd").is_file() and (APP_DIR.parent / "cheat.gd").is_file():
        RES_DIR = APP_DIR.parent
    tools_dir = APP_DIR.parent / "tools"
    if tools_dir.is_dir() and str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))

import build_cheat  # noqa: E402

CHEAT_GD = RES_DIR / "cheat.gd"
if getattr(sys, "frozen", False):
    ICON_PNG = RES_DIR / "sobosuba_mod_small.png"
    ICON_ICO = RES_DIR / "sobosuba_mod.ico"
else:
    ICON_PNG = APP_DIR.parent / "icons" / "sobosuba_mod_small.png"
    ICON_ICO = APP_DIR.parent / "icons" / "sobosuba_mod.ico"
LOCAL_APP = Path(os.environ.get("LOCALAPPDATA", str(APP_DIR)))
CACHE_DIR = LOCAL_APP / "SOBOSUBA修改器" / "cache"
CACHE_EXE = CACHE_DIR / "sobosuba.exe"
CACHE_META = CACHE_DIR / "cache_meta.json"
BACKUP_DIR = APP_DIR / "backups"
LOG_PATH = APP_DIR / "trainer_log.txt"
USER_DATA = Path(os.environ.get("APPDATA", "")) / "Godot" / "app_userdata" / "sobosuba"

CMD_PORT = 24680

DEFAULT_GAME_CANDIDATES = [
    Path(r"E:\SteamLibrary\steamapps\common\sobosuba\sobosuba.exe"),
    Path(r"C:\SteamLibrary\steamapps\common\sobosuba\sobosuba.exe"),
    Path(r"D:\game\ABS\sobosuba\sobosuba.exe"),
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

HELP_TEXT = """这是什么
这是一个独立的 SOBOSUBA 修改器。双击打开即可使用，不需要给原版游戏打补丁。
首次启动时，修改器会读取你电脑上的原版 sobosuba.exe，在本机缓存目录生成一份
“带修改器”的游戏副本并启动它。原版游戏文件完全不会被修改。

使用步骤
1. 选择原版 sobosuba.exe（默认自动识别 Steam 正式版）。
2. 点击「启动游戏（带修改器）」。
   首次会花几秒钟生成缓存副本；以后直接启动。
3. 游戏打开后，修改器会自动连接，下方的按钮可以实时生效：
   设置分数、加速/慢动作、解锁全部、生成球、关重力、冻结挡板等。
4. 游戏内也可以按：
   F2  打开/关闭内置作弊菜单
   F3  在鼠标位置生成球
   F1 / F4  打开开发者控制台

更换设备
把本工具文件夹复制到另一台电脑，运行 EXE 后选择那台电脑上的
sobosuba.exe，修改器会自动在那台电脑生成本地副本。原版始终不动。

缓存与备份
· 带修改器的游戏副本保存在：
  %LOCALAPPDATA%\\SOBOSUBA修改器\\cache
· 存档备份保存在本工具目录的 backups 文件夹。
· 想恢复干净状态：点击「清理缓存」即可，原版游戏不受影响。

注意
· 打补丁的只是缓存副本，不是原版文件；卸载修改器只需删除本工具文件夹。
· 仅限单人游戏娱乐使用。
"""


# ------------------------------------------------------------
# 基础工具
# ------------------------------------------------------------
def write_log(message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}\n"
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass
    try:
        if sys.stdout:
            print(line, end="")
    except Exception:
        pass


def find_default_game() -> Path | None:
    for candidate in DEFAULT_GAME_CANDIDATES:
        if candidate.is_file():
            return candidate
    return None


def is_game_running() -> bool:
    try:
        result = subprocess.run(
            ["tasklist"], capture_output=True, text=True, errors="ignore", timeout=10
        )
        text = (result.stdout or "").lower()
        return "sobosuba.exe" in text or "sobosuba.cheat.exe" in text
    except Exception:
        return False


def file_md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def source_signature(source_exe: Path) -> dict:
    stat = source_exe.stat()
    return {
        "path": str(source_exe.resolve()),
        "size": stat.st_size,
        "mtime": int(stat.st_mtime),
        "cheat_md5": file_md5(CHEAT_GD) if CHEAT_GD.is_file() else "",
    }


def cache_valid(source_exe: Path | None) -> bool:
    if not CACHE_EXE.is_file() or not CACHE_META.is_file():
        return False
    if source_exe is None or not source_exe.is_file():
        return True  # 缓存存在即可启动；没有原版时允许直接使用缓存
    try:
        meta = json.loads(CACHE_META.read_text(encoding="utf-8"))
    except Exception:
        return False
    return meta == source_signature(source_exe)


def build_cache(source_exe: Path, report=write_log) -> None:
    """从原版 exe 生成带修改器的缓存副本（不修改原版）。"""
    if not source_exe.is_file():
        raise RuntimeError(f"找不到原版 exe：{source_exe}")
    if not CHEAT_GD.is_file():
        raise RuntimeError(f"缺少内置脚本 cheat.gd：{CHEAT_GD}")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    temp_exe = CACHE_DIR / "sobosuba.building.exe"
    report(f"正在准备带修改器的游戏副本：{source_exe}")
    try:
        build_cheat.build(
            str(source_exe), str(temp_exe), str(CHEAT_GD),
            icon_png=str(ICON_PNG),
        )
        try:
            os.replace(temp_exe, CACHE_EXE)
        except PermissionError as exc:
            raise RuntimeError(
                "缓存中的游戏正在运行，无法更新。请先关闭修改器游戏再重试。"
            ) from exc
    finally:
        if temp_exe.exists():
            try:
                temp_exe.unlink()
            except OSError:
                pass

    # 复制 Steam / Godot 运行所需的 DLL 与 appid
    copied = []
    for item in source_exe.parent.iterdir():
        if not item.is_file():
            continue
        if item.suffix.lower() == ".dll" or item.name.lower() == "steam_appid.txt":
            shutil.copy2(item, CACHE_DIR / item.name)
            copied.append(item.name)
    if not copied:
        report("警告：原版目录没有找到 DLL / steam_appid.txt，缓存游戏可能无法启动。")
    meta = source_signature(source_exe)
    CACHE_META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    report("缓存副本生成完成。原版游戏文件未被修改。")


def launch_cache(extra_args: list[str] | None = None) -> subprocess.Popen:
    return subprocess.Popen(
        [str(CACHE_EXE)] + (extra_args or []),
        cwd=str(CACHE_DIR),
    )


# ------------------------------------------------------------
# 本地 TCP 命令通道
# ------------------------------------------------------------
def send_command(command: str, timeout: float = 2.5) -> str:
    try:
        with socket.create_connection(("127.0.0.1", CMD_PORT), timeout=timeout) as sock:
            sock.sendall((command + "\n").encode("utf-8"))
            sock.settimeout(timeout)
            data = b""
            while not data.endswith(b"\n"):
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
            return data.decode("utf-8", "replace").strip()
    except Exception as exc:
        return f"ERR {exc}"


def server_running(timeout: float = 0.6) -> bool:
    return send_command("ping", timeout).startswith("OK")


def wait_for_server(timeout: float = 45.0, report=write_log) -> bool:
    start = time.time()
    last_report = 0.0
    while time.time() - start < timeout:
        if send_command("ping", 1.0).startswith("OK"):
            report("修改器已连接游戏。")
            return True
        if time.time() - last_report >= 5.0:
            report("等待游戏启动…")
            last_report = time.time()
        time.sleep(1.0)
    return False


# ------------------------------------------------------------
# 存档备份
# ------------------------------------------------------------
def backup_saves() -> Path:
    if not USER_DATA.is_dir():
        raise RuntimeError(f"找不到存档目录：{USER_DATA}")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = BACKUP_DIR / f"save_{stamp}"
    index = 1
    while target.exists():
        target = BACKUP_DIR / f"save_{stamp}_{index}"
        index += 1
    target.mkdir(parents=True, exist_ok=True)
    for item in SAVE_ITEMS:
        source = USER_DATA / item
        if not source.exists():
            continue
        if source.is_dir():
            shutil.copytree(source, target / item, dirs_exist_ok=True)
        else:
            shutil.copy2(source, target / item)
    return target


def list_save_backups() -> list[Path]:
    if not BACKUP_DIR.is_dir():
        return []
    return sorted(
        [p for p in BACKUP_DIR.glob("save_*") if p.is_dir()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def restore_save_backup(backup: Path) -> None:
    if is_game_running():
        raise RuntimeError("请先关闭游戏，再恢复存档。")
    if not backup.is_dir():
        raise RuntimeError(f"备份目录不存在：{backup}")
    for item in SAVE_ITEMS:
        source = backup / item
        if not source.exists():
            continue
        target = USER_DATA / item
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            shutil.copy2(source, target)


# ------------------------------------------------------------
# GUI
# ------------------------------------------------------------
class PortableTrainerGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("SOBOSUBA 独立修改器")
        self.root.geometry("1000x780")
        self.root.minsize(900, 700)
        self.root.configure(bg=COLORS["bg"])
        self.game_exe_var = tk.StringVar()
        self.status_var = tk.StringVar(value="未连接")
        self.score_var = tk.StringVar(value="10000")
        self.tier_var = tk.IntVar(value=4)
        self._ui_queue: queue.Queue = queue.Queue()
        self._game_process: subprocess.Popen | None = None
        self._busy = False
        self._ever_launched = False

        self._setup_style()
        self._build_ui()
        default_game = find_default_game()
        if default_game:
            self.game_exe_var.set(str(default_game))
        self._log("修改器已就绪。首次启动会自动生成缓存副本，原版游戏不会被修改。")
        self.root.after(150, self._drain_ui_queue)
        self.root.after(2500, self._poll_status)

    # ------------------------------------------------------------
    # 样式
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
            font=("Microsoft YaHei UI", 10, "bold")
        )
        style.configure(
            "TButton", font=("Microsoft YaHei UI", 10), padding=(10, 6),
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
            darkcolor=COLORS["accent_dark"], padding=(14, 9)
        )
        style.map(
            "Accent.TButton",
            background=[("active", "#5fe3f2"), ("disabled", "#1d4c54")],
            foreground=[("disabled", "#0b1016")],
        )
        style.configure(
            "Warn.TButton", font=("Microsoft YaHei UI", 10, "bold"),
            background="#7a3b2e", foreground="#ffe8e0",
            bordercolor="#7a3b2e", lightcolor="#7a3b2e", darkcolor="#5a2b21",
            padding=(10, 6)
        )
        style.configure(
            "TEntry", fieldbackground=COLORS["panel2"], foreground=COLORS["text"],
            insertcolor=COLORS["text"], bordercolor=COLORS["panel2"], padding=6
        )
        style.configure(
            "TSpinbox", fieldbackground=COLORS["panel2"], foreground=COLORS["text"],
            background=COLORS["panel2"], padding=5
        )
        style.configure(
            "TLabelframe", background=COLORS["panel"], bordercolor=COLORS["panel2"],
            relief="solid", borderwidth=1
        )
        style.configure(
            "TLabelframe.Label", background=COLORS["panel"],
            foreground=COLORS["accent"], font=("Microsoft YaHei UI", 10, "bold")
        )
        style.configure("TNotebook", background=COLORS["bg"], borderwidth=0)
        style.configure(
            "TNotebook.Tab", background=COLORS["panel"], foreground=COLORS["muted"],
            padding=(18, 8), font=("Microsoft YaHei UI", 10)
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", COLORS["panel2"])],
            foreground=[("selected", COLORS["accent"])],
        )

    # ------------------------------------------------------------
    # 界面
    # ------------------------------------------------------------
    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=16)
        outer.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(outer)
        header.pack(fill=tk.X)
        ttk.Label(header, text="SOBOSUBA 独立修改器", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(
            header,
            text="双击即用 · 原版文件不改 · 本机缓存副本 · 其他设备自动适配",
            style="Sub.TLabel",
        ).pack(anchor=tk.W, pady=(2, 10))

        path_frame = ttk.Frame(outer)
        path_frame.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(path_frame, text="原版游戏").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Entry(path_frame, textvariable=self.game_exe_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        ttk.Button(path_frame, text="浏览…", command=self._browse).pack(
            side=tk.LEFT, padx=(8, 0)
        )

        launch_frame = ttk.Frame(outer)
        launch_frame.pack(fill=tk.X, pady=(0, 8))
        self.launch_btn = ttk.Button(
            launch_frame, text="启动游戏（带修改器）", style="Accent.TButton",
            command=self._launch_game
        )
        self.launch_btn.pack(side=tk.LEFT)
        ttk.Button(
            launch_frame, text="重建缓存", command=self._rebuild_cache
        ).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(
            launch_frame, text="打开缓存目录", command=self._open_cache_dir
        ).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(
            launch_frame, text="清理缓存", command=self._clean_cache
        ).pack(side=tk.LEFT, padx=(8, 0))

        ttk.Label(outer, textvariable=self.status_var, style="Status.TLabel").pack(
            anchor=tk.W, pady=(0, 8)
        )

        notebook = ttk.Notebook(outer)
        notebook.pack(fill=tk.BOTH, expand=True)

        cheat_frame = ttk.Frame(notebook, padding=10)
        notebook.add(cheat_frame, text="实时作弊")
        self._build_cheat_tab(cheat_frame)

        save_frame = ttk.Frame(notebook, padding=10)
        notebook.add(save_frame, text="存档/备份")
        self._build_save_tab(save_frame)

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
            text="原版游戏文件不会被修改 · 缓存位置：%LOCALAPPDATA%\\SOBOSUBA修改器\\cache · 仅限单人娱乐",
            style="Sub.TLabel",
        ).pack(anchor=tk.W, pady=(8, 0))

    def _build_cheat_tab(self, parent: ttk.Frame) -> None:
        # 分数
        score_box = ttk.LabelFrame(parent, text="分数", padding=10)
        score_box.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(score_box, text="当前分数").pack(side=tk.LEFT)
        ttk.Entry(score_box, textvariable=self.score_var, width=12).pack(
            side=tk.LEFT, padx=(8, 8)
        )
        ttk.Button(score_box, text="设置分数", command=self._set_score).pack(side=tk.LEFT)
        ttk.Button(score_box, text="+1000", command=lambda: self._send("score_add 1000")).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        ttk.Button(score_box, text="+10000", command=lambda: self._send("score_add 10000")).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        ttk.Button(score_box, text="刷新状态", command=self._poll_status_once).pack(
            side=tk.LEFT, padx=(8, 0)
        )

        # 速度
        speed_box = ttk.LabelFrame(parent, text="速度 / 时间倍率", padding=10)
        speed_box.pack(fill=tk.X, pady=(0, 8))
        for label, value in [("0.25x", 0.25), ("0.5x", 0.5), ("1x", 1.0), ("2x", 2.0), ("4x", 4.0)]:
            ttk.Button(
                speed_box, text=label,
                command=lambda v=value: self._send(f"time {v}")
            ).pack(side=tk.LEFT, padx=(0, 6))

        # 解锁
        unlock_box = ttk.LabelFrame(parent, text="解锁", padding=10)
        unlock_box.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(
            unlock_box, text="解锁全部样式 + 成就 + 生成档位",
            command=lambda: self._send("unlock_all")
        ).pack(side=tk.LEFT)

        # 球
        ball_box = ttk.LabelFrame(parent, text="球", padding=10)
        ball_box.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(ball_box, text="等级").pack(side=tk.LEFT)
        ttk.Spinbox(
            ball_box, from_=0, to=13, textvariable=self.tier_var, width=5
        ).pack(side=tk.LEFT, padx=(6, 8))
        ttk.Button(ball_box, text="在场地中央生成", command=self._spawn_ball).pack(side=tk.LEFT)
        ttk.Button(
            ball_box, text="清空所有球",
            command=lambda: self._send("clear_sobos")
        ).pack(side=tk.LEFT, padx=(8, 0))

        # 玩法
        play_box = ttk.LabelFrame(parent, text="玩法", padding=10)
        play_box.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(
            play_box, text="关闭重力", command=lambda: self._send("gravity 0")
        ).pack(side=tk.LEFT)
        ttk.Button(
            play_box, text="恢复重力", command=lambda: self._send("gravity_restore")
        ).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(
            play_box, text="冻结挡板", command=lambda: self._send("freeze_bumpers 1")
        ).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(
            play_box, text="解冻挡板", command=lambda: self._send("freeze_bumpers 0")
        ).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(
            play_box, text="关闭合并", command=lambda: self._send("merging 0")
        ).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(
            play_box, text="开启合并", command=lambda: self._send("merging 1")
        ).pack(side=tk.LEFT, padx=(6, 0))

        play_box2 = ttk.Frame(parent)
        play_box2.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(
            play_box2, text="冻结所有球", command=lambda: self._send("freeze_all 1")
        ).pack(side=tk.LEFT)
        ttk.Button(
            play_box2, text="解冻所有球", command=lambda: self._send("freeze_all 0")
        ).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(
            play_box2, text="结束本局", style="Warn.TButton",
            command=lambda: self._send("game_over")
        ).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(
            play_box2, text="打开游戏控制台", command=lambda: self._send("console_open")
        ).pack(side=tk.LEFT, padx=(6, 0))

    def _build_save_tab(self, parent: ttk.Frame) -> None:
        save_box = ttk.LabelFrame(parent, text="游戏内存档", padding=12)
        save_box.pack(fill=tk.X, pady=(0, 10))
        ttk.Button(save_box, text="保存进度", command=lambda: self._send("save")).pack(side=tk.LEFT)
        ttk.Button(save_box, text="读取进度", command=lambda: self._send("load")).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        ttk.Button(save_box, text="删除存档", command=lambda: self._send("delete_save")).pack(
            side=tk.LEFT, padx=(8, 0)
        )

        backup_box = ttk.LabelFrame(parent, text="存档备份（修改器目录 backups）", padding=12)
        backup_box.pack(fill=tk.X, pady=(0, 10))
        ttk.Button(backup_box, text="备份当前存档", command=self._backup_saves).pack(side=tk.LEFT)
        ttk.Button(backup_box, text="恢复最新备份", command=self._restore_saves).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        ttk.Button(backup_box, text="打开存档目录", command=self._open_user_dir).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        ttk.Button(backup_box, text="打开备份目录", command=self._open_backup_dir).pack(
            side=tk.LEFT, padx=(8, 0)
        )

        note = ttk.Label(
            parent,
            text="提示：备份/恢复存档请先关闭游戏；恢复会覆盖当前进度。\n"
                 "修改器本身不会修改原版游戏文件，缓存副本位于 %LOCALAPPDATA%\\SOBOSUBA修改器\\cache。",
            style="Sub.TLabel", wraplength=860, justify=tk.LEFT,
        )
        note.pack(anchor=tk.W, pady=(6, 0))

    def _open_backup_dir(self) -> None:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(str(BACKUP_DIR))

    # ------------------------------------------------------------
    # 路径 / 状态
    # ------------------------------------------------------------
    def _source_exe(self) -> Path | None:
        value = self.game_exe_var.get().strip().strip('"')
        if not value:
            return None
        path = Path(value)
        if path.is_dir():
            path = path / "sobosuba.exe"
        return path

    def _browse(self) -> None:
        current = self._source_exe()
        initial = str(current.parent) if current else ""
        selected = filedialog.askopenfilename(
            title="选择原版 sobosuba.exe",
            initialdir=initial,
            filetypes=[("sobosuba", "sobosuba*.exe"), ("可执行文件", "*.exe")],
        )
        if selected:
            self.game_exe_var.set(selected)
            self._log(f"已选择原版：{selected}")

    def _open_cache_dir(self) -> None:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(str(CACHE_DIR))

    def _open_user_dir(self) -> None:
        if not USER_DATA.is_dir():
            messagebox.showerror("找不到存档", f"存档目录不存在：\n{USER_DATA}")
            return
        os.startfile(str(USER_DATA))

    def _clean_cache(self) -> None:
        if self._game_process is not None and self._game_process.poll() is None:
            messagebox.showwarning("游戏正在运行", "请先关闭修改器游戏，再清理缓存。")
            return
        if not CACHE_DIR.is_dir():
            messagebox.showinfo("没有缓存", "缓存目录不存在，无需清理。")
            return
        if not messagebox.askyesno(
            "清理缓存",
            "将删除本机生成的带修改器游戏副本。\n原版游戏不会被删除。继续吗？",
        ):
            return
        try:
            shutil.rmtree(CACHE_DIR)
            self._log("缓存已清理。")
            self.status_var.set("缓存已清理")
        except Exception as exc:
            messagebox.showerror("清理失败", str(exc))

    # ------------------------------------------------------------
    # 启动 / 连接
    # ------------------------------------------------------------
    def _launch_game(self) -> None:
        if self._busy:
            return
        if server_running():
            self._log("检测到已有修改器游戏在运行，直接连接。")
            self._poll_status_once()
            return
        source = self._source_exe()
        if source is None or (not source.is_file() and not CACHE_EXE.is_file()):
            messagebox.showerror(
                "路径错误",
                "请选择有效的原版 sobosuba.exe。\n"
                "如果只是使用已有缓存，请确认缓存目录中的游戏仍然存在。",
            )
            return
        if is_game_running():
            if not messagebox.askyesno(
                "检测到游戏正在运行",
                "建议先关闭正在运行的原版游戏，避免两个实例共用存档。\n\n仍要继续吗？",
            ):
                return
        self._busy = True
        self.launch_btn.configure(state=tk.DISABLED)
        self.status_var.set("正在准备修改器游戏…")
        self._log("开始启动流程…")
        threading.Thread(
            target=self._launch_worker, args=(source,), daemon=True
        ).start()

    def _launch_worker(self, source: Path) -> None:
        try:
            need_build = not cache_valid(source) or not CACHE_EXE.is_file()
            if need_build:
                if not source.is_file():
                    raise RuntimeError(
                        "没有找到原版 exe，且本地缓存不可用。\n请先选择原版 sobosuba.exe。"
                    )
                build_cache(source, report=self._thread_log)
            else:
                self._thread_log("使用已有的带修改器游戏缓存。")
            self._thread_log("启动带修改器的游戏…")
            process = launch_cache()
            self._ui_queue.put(("process", process))
            if wait_for_server(50.0, report=self._thread_log):
                self._ui_queue.put(("launch_done", True))
            else:
                self._ui_queue.put(("launch_done", False))
        except Exception as exc:
            self._ui_queue.put(("launch_failed", str(exc)))

    def _rebuild_cache(self) -> None:
        if self._busy:
            return
        source = self._source_exe()
        if source is None or not source.is_file():
            messagebox.showerror("路径错误", "请选择有效的原版 sobosuba.exe。")
            return
        if self._game_process is not None and self._game_process.poll() is None:
            messagebox.showwarning("游戏正在运行", "请先关闭修改器游戏，再重建缓存。")
            return
        if is_game_running():
            messagebox.showwarning("游戏正在运行", "请先关闭游戏，再重建缓存。")
            return
        if not messagebox.askyesno(
            "重建缓存",
            "将从原版 exe 重新生成带修改器的游戏副本。\n原版文件不会被修改。继续吗？",
        ):
            return
        self._busy = True
        self.launch_btn.configure(state=tk.DISABLED)
        self.status_var.set("正在重建缓存…")
        threading.Thread(
            target=self._rebuild_worker, args=(source,), daemon=True
        ).start()

    def _rebuild_worker(self, source: Path) -> None:
        try:
            build_cache(source, report=self._thread_log)
            self._ui_queue.put(("rebuild_done", True))
        except Exception as exc:
            self._ui_queue.put(("rebuild_failed", str(exc)))

    # ------------------------------------------------------------
    # 命令发送
    # ------------------------------------------------------------
    def _send(self, command: str) -> None:
        reply = send_command(command)
        self._log(f"> {command}")
        self._log(f"< {reply}")
        if reply.startswith("ERR"):
            self.status_var.set("未连接：请先点击「启动游戏（带修改器）」")
        else:
            self._update_status_from_reply(reply)

    def _set_score(self) -> None:
        text = self.score_var.get().strip()
        if not text.is_valid_int():
            messagebox.showerror("输入错误", "请输入有效的整数分数。")
            return
        self._send(f"score_set {int(text)}")

    def _spawn_ball(self) -> None:
        try:
            tier = int(self.tier_var.get())
        except Exception:
            tier = 4
        self._send(f"spawn {tier}")

    def _poll_status_once(self) -> None:
        reply = send_command("status", 1.0)
        if reply.startswith("OK"):
            self._update_status_from_reply(reply)
        else:
            self.status_var.set("未连接：请先点击「启动游戏（带修改器）」")

    def _update_status_from_reply(self, reply: str) -> None:
        if not reply.startswith("OK"):
            return
        fields = {}
        for part in reply[2:].strip().split(" "):
            if "=" in part:
                key, value = part.split("=", 1)
                fields[key] = value
        score = fields.get("score", "?")
        time_scale = fields.get("time", "?")
        self.status_var.set(f"已连接 · 分数 {score} · 时间倍率 {time_scale}")

    def _poll_status(self) -> None:
        try:
            if self._game_process is not None and self._game_process.poll() is not None:
                self._game_process = None
                if not server_running(0.3):
                    self.status_var.set("游戏已退出 · 未连接")
            elif server_running(0.3):
                self._poll_status_once()
            else:
                if self._ever_launched:
                    self.status_var.set("未连接：请检查游戏是否已启动")
        except Exception:
            pass
        try:
            self.root.after(2500, self._poll_status)
        except tk.TclError:
            pass

    # ------------------------------------------------------------
    # 存档备份
    # ------------------------------------------------------------
    def _backup_saves(self) -> None:
        try:
            target = backup_saves()
        except Exception as exc:
            messagebox.showerror("备份失败", str(exc))
            return
        self._log(f"存档已备份：{target}")
        messagebox.showinfo("备份完成", f"存档已备份到：\n{target}")

    def _restore_saves(self) -> None:
        backups = list_save_backups()
        if not backups:
            messagebox.showerror("没有备份", "还没有存档备份。")
            return
        if is_game_running():
            messagebox.showerror("游戏正在运行", "请先关闭游戏，再恢复存档。")
            return
        latest = backups[0]
        if not messagebox.askyesno(
            "恢复存档",
            f"将用以下备份覆盖当前存档：\n{latest}\n\n继续吗？",
        ):
            return
        try:
            restore_save_backup(latest)
        except Exception as exc:
            messagebox.showerror("恢复失败", str(exc))
            return
        self._log(f"存档已恢复：{latest}")
        messagebox.showinfo("恢复完成", "存档已恢复。")

    # ------------------------------------------------------------
    # 日志 / 队列
    # ------------------------------------------------------------
    def _append_log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        text = f"[{timestamp}] {message}\n"
        try:
            self.log_text.configure(state=tk.NORMAL)
            self.log_text.insert(tk.END, text)
            self.log_text.see(tk.END)
            self.log_text.configure(state=tk.DISABLED)
        except tk.TclError:
            pass
        write_log(message)

    def _log(self, message: str) -> None:
        self._ui_queue.put(("log", message))

    def _thread_log(self, message: str) -> None:
        self._ui_queue.put(("log", message))

    def _drain_ui_queue(self) -> None:
        try:
            while True:
                kind, payload = self._ui_queue.get_nowait()
                if kind == "log":
                    self._append_log(payload)
                elif kind == "process":
                    self._game_process = payload
                    self._ever_launched = True
                elif kind == "launch_done":
                    self._busy = False
                    self.launch_btn.configure(state=tk.NORMAL)
                    if payload:
                        self._poll_status_once()
                        self._log("修改器已连接，可以使用下方按钮或游戏内 F2 菜单。")
                    else:
                        self.status_var.set("启动超时：请查看运行日志")
                        self._log("等待游戏命令端口超时，请检查游戏是否成功启动。")
                elif kind == "launch_failed":
                    self._busy = False
                    self.launch_btn.configure(state=tk.NORMAL)
                    self.status_var.set("启动失败")
                    self._log(f"启动失败：{payload}")
                    messagebox.showerror("启动失败", str(payload))
                elif kind == "rebuild_done":
                    self._busy = False
                    self.launch_btn.configure(state=tk.NORMAL)
                    self.status_var.set("缓存已重建")
                elif kind == "rebuild_failed":
                    self._busy = False
                    self.launch_btn.configure(state=tk.NORMAL)
                    self.status_var.set("缓存重建失败")
                    messagebox.showerror("重建失败", str(payload))
        except queue.Empty:
            pass
        try:
            self.root.after(150, self._drain_ui_queue)
        except tk.TclError:
            pass


# ------------------------------------------------------------
# 自检 / 命令行
# ------------------------------------------------------------
def selftest(source_exe: Path) -> int:
    write_log("=== 修改器自检开始 ===")
    try:
        build_cache(source_exe, report=write_log)
        process = launch_cache(["--headless"])
        write_log(f"已启动缓存游戏，PID={process.pid}")
        ok = wait_for_server(60.0, report=write_log)
        if not ok:
            write_log("自检失败：命令端口未就绪")
            process.terminate()
            return 1
        results = {}
        for command in ["status", "score_set 12345", "status", "time 0.5", "status"]:
            reply = send_command(command)
            results[command] = reply
            write_log(f"{command} => {reply}")
        process.terminate()
        try:
            process.wait(timeout=5)
        except Exception:
            process.kill()
        if results.get("score_set 12345", "").startswith("OK") and "score=12345" in results.get("status", ""):
            write_log("=== 自检成功 ===")
            return 0
        write_log("=== 自检失败：分数未正确设置 ===")
        return 1
    except Exception as exc:
        write_log(f"自检异常：{exc}")
        return 1


def main() -> None:
    parser = argparse.ArgumentParser(description="SOBOSUBA 独立修改器")
    parser.add_argument("--selftest", metavar="EXE", help="用指定原版 exe 做端到端自检")
    args = parser.parse_args()
    if args.selftest:
        sys.exit(selftest(Path(args.selftest)))

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
    PortableTrainerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
