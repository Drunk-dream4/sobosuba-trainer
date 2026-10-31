#!/usr/bin/env python3
"""Godot 4 PCK 解包 / 打包 / 内嵌工具（用于 sobosuba 修改器）。

支持 Godot 4.4+ 的 PCK 格式版本 4（PACK_REL_FILEBASE）。
用法见文件末尾的命令行入口。
"""

import argparse
import hashlib
import os
import struct
import sys

HEADER_SIZE = 112


class PckEntry:
    """PCK 目录中的一条文件记录。"""

    def __init__(self, raw_path, offset, size, md5, flags):
        self.raw_path = raw_path  # 原始路径字节（可能包含结尾的 \x00 填充）
        self.offset = offset      # 相对于 pck 起点 + file_base 的偏移
        self.size = size
        self.md5 = md5
        self.flags = flags

    @property
    def path(self):
        return self.raw_path.rstrip(b"\x00").decode("utf-8", "replace")


def read_pck_bytes(data, pck_start=0):
    """解析 PCK，返回 (header, entries)。data 为整个文件内容。"""
    magic, pack_version, major, minor, patch, flags = struct.unpack_from(
        "<4sIIIII", data, pck_start
    )
    if magic != b"GDPC":
        raise ValueError("不是有效的 PCK 文件（缺少 GDPC 魔数）")
    if pack_version != 4:
        raise ValueError(f"暂不支持 PCK 格式版本 {pack_version}，仅支持 4")
    file_base, dir_offset = struct.unpack_from("<QQ", data, pck_start + 24)
    pos = pck_start + dir_offset
    file_count = struct.unpack_from("<I", data, pos)[0]
    pos += 4
    entries = []
    for _ in range(file_count):
        path_len = struct.unpack_from("<I", data, pos)[0]
        pos += 4
        raw_path = data[pos:pos + path_len]
        pos += path_len
        pos = (pos + 3) & ~3
        offset, size = struct.unpack_from("<QQ", data, pos)
        pos += 16
        md5 = data[pos:pos + 16]
        pos += 16
        entry_flags = struct.unpack_from("<I", data, pos)[0]
        pos += 4
        entries.append(PckEntry(raw_path, offset, size, md5, entry_flags))
    header = {
        "pack_version": pack_version,
        "major": major,
        "minor": minor,
        "patch": patch,
        "flags": flags,
        "file_base": file_base,
        "dir_offset": dir_offset,
        "file_count": file_count,
    }
    return header, entries


def extract_pck(pck_path, out_dir, pck_start=0):
    """把 PCK 内所有文件解包到 out_dir。返回条目数。"""
    data = open(pck_path, "rb").read()
    header, entries = read_pck_bytes(data, pck_start)
    base = pck_start + header["file_base"]
    os.makedirs(out_dir, exist_ok=True)
    for entry in entries:
        rel = entry.path.replace("res://", "").replace("/", os.sep)
        # 防止路径穿越
        if ".." in rel.split(os.sep):
            continue
        dst = os.path.join(out_dir, rel)
        parent = os.path.dirname(dst)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(dst, "wb") as f:
            f.write(data[base + entry.offset:base + entry.offset + entry.size])
    return len(entries)


def build_pck(entries, payloads, out_path, major=4, minor=7, patch=2, flags=2):
    """根据条目列表与文件数据重新打包 PCK。

    entries: 原始 PckEntry 列表（保留路径与 MD5）
    payloads: {entry.path: bytes}，未提供的文件从原 PCK 读取
    返回新 PCK 的字节内容。
    """
    file_base = HEADER_SIZE
    body = bytearray()
    new_meta = []  # (entry, new_offset, payload, md5)
    for entry in entries:
        if entry.path not in payloads:
            raise KeyError(f"缺少文件内容: {entry.path}")
        payload = payloads[entry.path]
        # 4 字节对齐，便于引擎读取
        while len(body) % 4:
            body.append(0)
        offset = len(body)
        body.extend(payload)
        md5 = hashlib.md5(payload).digest()
        new_meta.append((entry, offset, len(payload), md5))

    while len(body) % 8:
        body.append(0)
    dir_offset = file_base + len(body)

    directory = bytearray()
    directory.extend(struct.pack("<I", len(new_meta)))
    for entry, offset, size, md5 in new_meta:
        raw = entry.raw_path
        directory.extend(struct.pack("<I", len(raw)))
        directory.extend(raw)
        while len(directory) % 4:
            directory.append(0)
        directory.extend(struct.pack("<QQ", offset, size))
        directory.extend(md5)
        directory.extend(struct.pack("<I", entry.flags))

    header = bytearray(HEADER_SIZE)
    struct.pack_into("<4sIIIII", header, 0, b"GDPC", 4, major, minor, patch, flags)
    struct.pack_into("<QQ", header, 24, file_base, dir_offset)
    return bytes(header) + bytes(body) + bytes(directory)


def read_all_payloads(pck_path, entries, pck_start=0):
    """读取 PCK 中所有文件内容，返回 {路径: bytes}。"""
    data = open(pck_path, "rb").read()
    header, _ = read_pck_bytes(data, pck_start)
    base = pck_start + header["file_base"]
    return {
        e.path: data[base + e.offset:base + e.offset + e.size] for e in entries
    }


def embed_pck_into_exe(exe_path, pck_bytes, out_exe):
    """把 PCK 内嵌进 exe 副本。

    Godot 在 exe 末尾用 [uint64 pck_size - 12][GDPC] 作为内嵌包定位标记。
    """
    data = open(exe_path, "rb").read()
    if data[-4:] != b"GDPC":
        raise ValueError("exe 末尾没有 GDPC 标记，无法确定内嵌 PCK 位置")
    # 末尾 12 字节 = [uint64 PCK 内容长度][GDPC]；PCK 内容不含这 12 字节
    old_content_size = struct.unpack_from("<Q", data, len(data) - 12)[0]
    pck_start = len(data) - old_content_size - 12
    trailer = struct.pack("<Q", len(pck_bytes)) + b"GDPC"
    with open(out_exe, "wb") as f:
        f.write(data[:pck_start])
        f.write(pck_bytes)
        f.write(trailer)
    return pck_start


def main():
    parser = argparse.ArgumentParser(description="Godot 4 PCK 工具")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_extract = sub.add_parser("extract", help="解包 PCK")
    p_extract.add_argument("pck")
    p_extract.add_argument("out")
    p_extract.add_argument("--start", type=int, default=0, help="PCK 在文件中的起始偏移")

    p_build = sub.add_parser("build", help="重新打包 PCK（可替换指定文件）")
    p_build.add_argument("pck")
    p_build.add_argument("out")
    p_build.add_argument("--replace", nargs=2, action="append", default=[],
                         help="res:// 路径 新文件路径")
    p_build.add_argument("--add", nargs=2, action="append", default=[],
                         help="新增文件：res:// 路径 本地文件路径")
    p_build.add_argument("--start", type=int, default=0)

    p_embed = sub.add_parser("embed", help="把 PCK 内嵌进 exe 副本")
    p_embed.add_argument("exe")
    p_embed.add_argument("pck")
    p_embed.add_argument("out")

    args = parser.parse_args()
    if args.cmd == "extract":
        n = extract_pck(args.pck, args.out, args.start)
        print(f"已解包 {n} 个文件到 {args.out}")
    elif args.cmd == "build":
        data = open(args.pck, "rb").read()
        header, entries = read_pck_bytes(data, args.start)
        payloads = read_all_payloads(args.pck, entries, args.start)
        for res_path, file_path in args.replace:
            res_path = res_path.replace("\\", "/")
            candidates = [res_path]
            if res_path.startswith("res://"):
                candidates.append(res_path[len("res://"):])
            else:
                candidates.append("res://" + res_path.lstrip("/"))
            actual = next((p for p in candidates if p in payloads), None)
            if actual is None:
                raise SystemExit(f"PCK 中不存在路径: {res_path}")
            payloads[actual] = open(file_path, "rb").read()
        for res_path, file_path in args.add:
            res_path = res_path.replace("\\", "/")
            if res_path.startswith("res://"):
                res_path = res_path[len("res://"):]
            res_path = res_path.lstrip("/")
            if res_path in payloads:
                raise SystemExit(f"路径已存在，请改用 --replace: {res_path}")
            raw = res_path.encode("utf-8")
            raw += b"\x00" * ((4 - len(raw) % 4) % 4)
            entries.append(PckEntry(raw, 0, 0, b"", 0))
            payloads[res_path] = open(file_path, "rb").read()
        pck = build_pck(entries, payloads, args.out, header["major"], header["minor"],
                        header["patch"], header["flags"])
        with open(args.out, "wb") as f:
            f.write(pck)
        print(f"已生成 {args.out}（{len(pck)} 字节，{len(entries)} 个文件）")
    elif args.cmd == "embed":
        pck_bytes = open(args.pck, "rb").read()
        start = embed_pck_into_exe(args.exe, pck_bytes, args.out)
        print(f"已生成 {args.out}，PCK 起始偏移 {start}")


if __name__ == "__main__":
    main()
