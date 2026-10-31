#!/usr/bin/env python3
"""从原版 sobosuba.exe 生成内置修改器版 exe。

原理：
  1. 读取原版 exe 末尾内嵌的 Godot PCK；
  2. 在 project.binary 中注册 autoload/Cheat -> *res://cheat.gd；
  3. 把 cheat.gd 加入 PCK；
  4. 重新打包并嵌入到新的 exe（原 exe 不会被修改）。

用法：
  python tools/build_cheat.py --game "E:\\SteamLibrary\\steamapps\\common\\sobosuba\\sobosuba.exe"
  python tools/build_cheat.py --game <sobosuba.exe> --out <sobosuba.cheat.exe>
"""

import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pck_tool import PckEntry, build_pck, read_pck_bytes, read_all_payloads, embed_pck_into_exe

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CHEAT = os.path.join(ROOT, "cheat.gd")

AUTOLOAD_KEY = "autoload/Cheat"
AUTOLOAD_PATH = "*res://cheat.gd"
CHEAT_RES_PATH = "cheat.gd"
ICON_PNG_RES_PATH = "sobosuba_mod_small.png"


def find_embedded_pck_start(exe_data):
    """根据 exe 末尾的 [uint64 PCK内容长度][GDPC] 定位内嵌 PCK。"""
    if exe_data[-4:] != b"GDPC":
        raise ValueError("exe 末尾没有 GDPC 标记，可能不是内嵌 PCK 的导出版本")
    content_size = struct.unpack_from("<Q", exe_data, len(exe_data) - 12)[0]
    start = len(exe_data) - content_size - 12
    if exe_data[start:start + 4] != b"GDPC":
        raise ValueError("定位到的 PCK 起始位置没有 GDPC 魔数")
    return start


def add_autoload(project_binary, name="Cheat", res_path="*res://cheat.gd"):
    """在 Godot 的 project.binary（ECFG 格式）末尾追加 autoload 条目。"""
    data = bytearray(project_binary)
    if data[:4] != b"ECFG":
        raise ValueError("project.binary 不是 ECFG 格式")
    count = struct.unpack_from("<I", data, 4)[0]

    # 检查是否已存在，避免重复添加
    off = 8
    for _ in range(count):
        key_len = struct.unpack_from("<I", data, off)[0]
        off += 4
        key = data[off:off + key_len].decode("utf-8", "replace")
        off += key_len
        value_len = struct.unpack_from("<I", data, off)[0]
        off += 4
        off += value_len
        if key == f"autoload/{name}":
            return bytes(data), False

    key_bytes = f"autoload/{name}".encode("utf-8")
    value = struct.pack("<I", 4) + struct.pack("<I", len(res_path.encode("utf-8")))
    value += res_path.encode("utf-8")
    while len(value) % 4:
        value += b"\x00"
    entry = struct.pack("<I", len(key_bytes)) + key_bytes
    entry += struct.pack("<I", len(value)) + value

    struct.pack_into("<I", data, 4, count + 1)
    data.extend(entry)
    return bytes(data), True


def ensure_cheat_entry(entries, payloads, cheat_source):
    """确保 PCK 中存在 cheat.gd，并返回更新后的条目/内容。"""
    payloads = dict(payloads)
    existing = next((e for e in entries if e.path == CHEAT_RES_PATH), None)
    if existing:
        payloads[CHEAT_RES_PATH] = open(cheat_source, "rb").read()
        return entries, payloads
    raw = CHEAT_RES_PATH.encode("utf-8")
    raw += b"\x00" * ((4 - len(raw) % 4) % 4)
    new_entry = PckEntry(raw, 0, 0, b"", 0)
    entries = list(entries) + [new_entry]
    payloads[CHEAT_RES_PATH] = open(cheat_source, "rb").read()
    return entries, payloads


def ensure_file_entry(entries, payloads, res_path, source_file):
    """确保 PCK 中存在指定路径的文件，并写入本地文件内容。"""
    payloads = dict(payloads)
    data = open(source_file, "rb").read()
    existing = next((e for e in entries if e.path == res_path), None)
    if existing:
        payloads[res_path] = data
        return entries, payloads
    raw = res_path.encode("utf-8")
    raw += b"\x00" * ((4 - len(raw) % 4) % 4)
    entries = list(entries) + [PckEntry(raw, 0, 0, b"", 0)]
    payloads[res_path] = data
    return entries, payloads


def build(game_exe, out_exe, cheat_source, icon_png=None):
    exe_data = open(game_exe, "rb").read()
    pck_start = find_embedded_pck_start(exe_data)
    header, entries = read_pck_bytes(exe_data, pck_start)
    payloads = read_all_payloads(game_exe, entries, pck_start)

    if "project.binary" not in payloads:
        raise ValueError("PCK 中没有 project.binary")

    patched_project, added = add_autoload(payloads["project.binary"])
    payloads["project.binary"] = patched_project

    entries, payloads = ensure_cheat_entry(entries, payloads, cheat_source)

    if icon_png:
        if not os.path.isfile(icon_png):
            raise FileNotFoundError(f"找不到图标 PNG：{icon_png}")
        entries, payloads = ensure_file_entry(
            entries, payloads, ICON_PNG_RES_PATH, icon_png
        )

    pck_bytes = build_pck(
        entries, payloads, out_exe,
        header["major"], header["minor"], header["patch"], header["flags"],
    )
    embed_pck_into_exe(game_exe, pck_bytes, out_exe)
    return {
        "pck_files": len(entries),
        "pck_size": len(pck_bytes),
        "autoload_added": added,
        "out_exe": out_exe,
        "out_size": os.path.getsize(out_exe),
        "icon_png": icon_png,
    }


def main():
    default_game = r"E:\SteamLibrary\steamapps\common\sobosuba\sobosuba.exe"
    parser = argparse.ArgumentParser(description="生成 sobosuba 内置修改器版 exe")
    parser.add_argument("--game", default=default_game, help="原版 sobosuba.exe 路径")
    parser.add_argument("--out", default="", help="输出 exe 路径，默认同目录 sobosuba.cheat.exe")
    parser.add_argument("--cheat", default=DEFAULT_CHEAT, help="cheat.gd 路径")
    parser.add_argument("--icon-png", default="", help="写入游戏 PCK 的窗口图标 PNG 路径")
    args = parser.parse_args()

    out_exe = args.out or os.path.join(os.path.dirname(args.game), "sobosuba.cheat.exe")
    if not os.path.isfile(args.game):
        raise SystemExit(f"找不到原版 exe: {args.game}")
    if not os.path.isfile(args.cheat):
        raise SystemExit(f"找不到 cheat.gd: {args.cheat}")

    result = build(
        args.game, out_exe, args.cheat,
        icon_png=args.icon_png or None,
    )
    print(f"生成成功: {result['out_exe']}")
    print(f"  大小: {result['out_size']} 字节")
    print(f"  PCK 文件数: {result['pck_files']}，PCK 大小: {result['pck_size']} 字节")
    print(f"  autoload/Cheat: {'已添加' if result['autoload_added'] else '已存在'}")
    print("启动后按 F2 打开修改器菜单，F3 生成球，F1 / F4 打开控制台。")


if __name__ == "__main__":
    main()
