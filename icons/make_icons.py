#!/usr/bin/env python3
"""生成 SOBOSUBA 修改器图标候选与预览图。

风格：深色圆角底 + 游戏彩色软球 + 青色齿轮工具元素。
所有图标均为本地绘制，无外部素材版权问题。
"""

import math
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent
S = 1024

BG_TOP = (11, 16, 22)
BG_BOTTOM = (22, 34, 46)
ACCENT = (53, 201, 220)
DARK = (11, 16, 22)
YELLOW = (255, 217, 59)
RED = (255, 107, 107)
GREEN = (110, 231, 168)
BLUE = (77, 195, 255)
PURPLE = (179, 136, 255)


def lerp_color(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def rounded_mask(size, radius):
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return mask


def base_background():
    grad = Image.new("RGB", (S, S))
    px = grad.load()
    for y in range(S):
        color = lerp_color(BG_TOP, BG_BOTTOM, y / (S - 1))
        for x in range(S):
            px[x, y] = color
    bg = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    bg.paste(grad, (0, 0), rounded_mask(S, int(S * 0.22)))
    draw = ImageDraw.Draw(bg)
    draw.rounded_rectangle(
        [int(S * 0.025), int(S * 0.025), int(S * 0.975), int(S * 0.975)],
        radius=int(S * 0.2), outline=ACCENT + (170,), width=max(2, int(S * 0.012))
    )
    return bg


def draw_blob(base, cx, cy, radius, color):
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.ellipse(
        [cx - radius * 1.05, cy - radius * 0.86, cx + radius * 1.05, cy + radius * 1.04],
        fill=(0, 0, 0, 95),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius * 0.16))
    base.alpha_composite(shadow)

    draw = ImageDraw.Draw(layer)
    draw.ellipse(
        [cx - radius, cy - radius * 0.94, cx + radius, cy + radius * 0.94],
        fill=color + (255,),
    )
    base.alpha_composite(layer)

    shine = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shine)
    sd.ellipse(
        [cx - radius * 0.58, cy - radius * 0.72, cx + radius * 0.18, cy - radius * 0.12],
        fill=(255, 255, 255, 105),
    )
    shine = shine.filter(ImageFilter.GaussianBlur(radius * 0.16))
    base.alpha_composite(shine)

    dot = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    dd = ImageDraw.Draw(dot)
    dd.ellipse(
        [cx - radius * 0.44, cy - radius * 0.58, cx - radius * 0.06, cy - radius * 0.26],
        fill=(255, 255, 255, 210),
    )
    dot = dot.filter(ImageFilter.GaussianBlur(radius * 0.05))
    base.alpha_composite(dot)


def draw_gear(container, cx, cy, radius, color, hole_color, hole_ratio=0.38, teeth=8):
    draw = ImageDraw.Draw(container)
    inner = radius * 0.76
    outer = radius
    half_angle = math.pi / teeth * 0.62
    for i in range(teeth):
        angle = 2 * math.pi * i / teeth
        points = []
        for a, r in [
            (angle - half_angle, inner),
            (angle - half_angle * 0.72, outer),
            (angle + half_angle * 0.72, outer),
            (angle + half_angle, inner),
        ]:
            points.append((cx + math.cos(a) * r, cy + math.sin(a) * r))
        draw.polygon(points, fill=color + (255,))
    draw.ellipse(
        [cx - inner, cy - inner, cx + inner, cy + inner], fill=color + (255,)
    )
    hole = inner * hole_ratio / 0.76
    draw.ellipse(
        [cx - hole, cy - hole, cx + hole, cy + hole], fill=hole_color + (255,)
    )


def badge_gear(base, cx, cy, radius):
    draw = ImageDraw.Draw(base)
    draw.ellipse(
        [cx - radius, cy - radius, cx + radius, cy + radius],
        fill=(9, 14, 20, 245), outline=ACCENT + (255,),
        width=max(3, int(S * 0.016)),
    )
    draw_gear(base, cx, cy, radius * 0.62, ACCENT, DARK, hole_ratio=0.4, teeth=8)


def icon_a():
    img = base_background()
    draw_blob(img, 360, 420, 205, BLUE)
    draw_blob(img, 520, 610, 225, GREEN)
    draw_blob(img, 660, 380, 190, RED)
    draw_blob(img, 430, 330, 195, YELLOW)
    badge_gear(img, 760, 760, 190)
    return img


def icon_b():
    img = base_background()
    draw_blob(img, 512, 470, 330, BLUE)
    # 内部叠加一层更亮的青色，制造软体果冻感
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([300, 250, 720, 660], fill=(90, 235, 255, 70))
    glow = glow.filter(ImageFilter.GaussianBlur(70))
    img.alpha_composite(glow)
    draw_blob(img, 760, 740, 150, YELLOW)
    badge_gear(img, 730, 730, 230)
    return img


def icon_c():
    img = base_background()
    draw_blob(img, 512, 480, 290, YELLOW)
    draw_blob(img, 420, 560, 190, RED)
    draw_blob(img, 620, 560, 190, GREEN)
    # 大齿轮环：中心留空，露出彩色软球
    gear = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw_gear(gear, 512, 500, 360, ACCENT, DARK, hole_ratio=1.05, teeth=10)
    # 把齿轮中心清空，露出后面的球
    center = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    cd = ImageDraw.Draw(center)
    cd.ellipse([512 - 240, 500 - 240, 512 + 240, 500 + 240], fill=(0, 0, 0, 255))
    gear = Image.composite(Image.new("RGBA", (S, S), (0, 0, 0, 0)), gear, center)
    img.alpha_composite(gear)
    return img


def icon_c_preview_fix():
    """icon_c 的齿轮环中心需要真正挖空；上面的合成方式改为 alpha mask。"""
    img = base_background()
    draw_blob(img, 512, 480, 290, YELLOW)
    draw_blob(img, 420, 560, 190, RED)
    draw_blob(img, 620, 560, 190, GREEN)
    gear = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw_gear(gear, 512, 500, 360, ACCENT, DARK, hole_ratio=0.0, teeth=10)
    # 用椭圆遮罩挖空中心
    hole = Image.new("L", (S, S), 255)
    hd = ImageDraw.Draw(hole)
    hd.ellipse([512 - 238, 500 - 238, 512 + 238, 500 + 238], fill=0)
    r, g, b, a = gear.split()
    a = Image.composite(a, Image.new("L", (S, S), 0), hole)
    gear = Image.merge("RGBA", (r, g, b, a))
    img.alpha_composite(gear)
    return img


def load_font(size, bold=False):
    candidates = [
        r"C:\Windows\Fonts\msyhbd.ttc" if bold else r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\msyh.ttc",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size, index=0)
            except Exception:
                pass
    return ImageFont.load_default()


def resize_icon(img, size):
    return img.resize((size, size), Image.LANCZOS)


def contact_sheet(icons):
    W, H = 1800, 820
    sheet = Image.new("RGB", (W, H), (12, 18, 25))
    draw = ImageDraw.Draw(sheet)
    title_font = load_font(34, True)
    label_font = load_font(24, True)
    sub_font = load_font(17)
    small_font = load_font(15)

    draw.text((60, 36), "SOBOSUBA 修改器 · 图标候选", font=title_font, fill=(232, 244, 248))
    draw.text((60, 84), "本地绘制 · 可放大查看 · 选出你想用在 EXE 上的方案", font=sub_font, fill=(138, 163, 176))

    names = [
        ("A", "彩色软球 + 齿轮", "更贴近游戏本身，三颗软球叠在一起，右下角加工具齿轮。", icons["A"]),
        ("B", "青色史莱姆 + 齿轮", "单颗大软球，高对比、远景更清楚，适合当修改器主图标。", icons["B"]),
        ("C", "软球 + 齿轮环", "彩色软球被青色齿轮环包围，工具感最强。", icons["C"]),
    ]
    col_x = [60, 640, 1220]
    for idx, (letter, title, desc, icon) in enumerate(names):
        x = col_x[idx]
        y = 150
        draw.rounded_rectangle(
            [x, y, x + 520, y + 620], radius=18, fill=(18, 27, 36),
            outline=(35, 48, 60), width=2,
        )
        draw.text((x + 24, y + 20), f"方案 {letter} · {title}", font=label_font, fill=(90, 225, 235))
        draw.text((x + 24, y + 56), desc, font=small_font, fill=(150, 172, 185))

        big = resize_icon(icon, 220)
        sheet.paste(big, (x + 150, y + 96), big)

        sizes = [96, 64, 48, 32, 16]
        sx = x + 24
        sy = y + 350
        draw.text((sx, sy - 26), "深色背景", font=small_font, fill=(120, 145, 160))
        for size in sizes:
            small = resize_icon(icon, size)
            sheet.paste(small, (sx, sy + (96 - size) // 2), small)
            sx += size + 18

        # 浅色背景检查
        draw.rounded_rectangle([x + 20, y + 460, x + 500, y + 520], radius=8, fill=(232, 238, 242))
        sx = x + 30
        for size in [64, 48, 32, 16]:
            small = resize_icon(icon, size)
            sheet.paste(small, (sx, y + 490 - size // 2), small)
            sx += size + 18
        draw.text((x + 24, y + 540), "浅色背景检查（任务栏/资源管理器）", font=small_font, fill=(120, 145, 160))

    sheet.save(ROOT / "preview.png")
    return ROOT / "preview.png"


def main():
    icons = {
        "A": icon_a(),
        "B": icon_b(),
        "C": icon_c_preview_fix(),
    }
    for key, icon in icons.items():
        icon.save(ROOT / f"icon_{key}.png")
    preview = contact_sheet(icons)
    print(preview)
    try:
        os.startfile(str(preview))
    except Exception:
        pass


if __name__ == "__main__":
    main()
