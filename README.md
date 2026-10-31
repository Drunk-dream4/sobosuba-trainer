# SOBOSUBA 修改器

面向 Godot 4.7.2 正式版《索博苏巴 / sobosuba》的修改器。提供两种用法：

- **独立修改器 EXE（推荐）**：双击即用，原版文件不改；在本机缓存目录生成带修改器的游戏副本，通过 127.0.0.1 命令通道实时控制。
- **内置修改器版（旧方案）**：向 PCK 注入 autoload，生成独立的 `sobosuba.cheat.exe`。

> 仅限单人游戏娱乐使用。

---

## 独立修改器（推荐，双击即用）

成品位置（仓库内）：

```text
sobosuba-trainer\SOBOSUBA修改器独立版\SOBOSUBA修改器.exe
```

使用方式：

1. 双击 `SOBOSUBA修改器.exe`，选择本机原版 `sobosuba.exe`（默认自动识别 Steam 正式版）。
2. 点击 **「启动游戏（带修改器）」**。首次会花几秒钟在 `%LOCALAPPDATA%\SOBOSUBA修改器\cache` 生成一份带修改器的游戏副本，**原版文件完全不动**。
3. 启动后修改器界面显示「已连接」，分数、速度、解锁、生成球、重力、冻结、合并等按钮实时生效。
4. 游戏内仍可按：

| 快捷键 | 功能 |
|--------|------|
| **F2** | 打开 / 关闭独立修改器窗口（系统窗口，可单独移动/置顶） |
| **F3** | 在鼠标位置生成球 |
| **F1 / F4** | 打开 / 关闭开发者控制台 |

换设备时，把整个 `SOBOSUBA修改器独立版` 文件夹复制到另一台电脑，
运行 EXE 并选择那台电脑上的原版 exe，修改器会自动重新生成本地缓存。

源码与重新打包：

```bash
cd sobosuba-trainer/standalone
python -m PyInstaller --noconfirm --onefile --windowed --name SOBOSUBA_Trainer ^
  --icon "../icons/sobosuba_mod.ico" ^
  --add-data "../icons/sobosuba_mod.ico;." ^
  --add-data "../icons/sobosuba_mod_small.png;." ^
  --paths "../tools" --add-data "../cheat.gd;." portable_trainer.py
```

源码：`standalone/portable_trainer.py`。打包后的 EXE 内嵌了 `cheat.gd`，不依赖本仓库其他文件。

图标：`icons/sobosuba_mod.ico`（方案 A：彩色软球 + 齿轮，含 16~256 多尺寸）。
预览：`icons/preview.png`、`icons/final_preview.png`；生成脚本：`icons/make_icons.py`。

---

## 内置修改器版（旧方案）

通过**向游戏 PCK 注入一个 autoload 脚本**来实现作弊菜单：

- 原版 `sobosuba.exe` **不会被修改**；
- 生成一个独立的 `sobosuba.cheat.exe`，与原版共存；
- 按 **F2** 打开独立的修改器窗口（系统窗口，可单独移动/置顶）；
- 同时重新启用了游戏自带的开发者控制台（**F1 / F4**）。

### 快速开始

已打包好的启动器（推荐直接使用）：

```text
sobosuba-trainer\SOBOSUBA修改器启动器\SOBOSUBA修改器启动器.exe
```

1. 双击 `SOBOSUBA修改器启动器.exe`（或源码方式双击 `启动修改器.bat`）。
2. 确认游戏目录（默认自动识别 Steam 正式版目录）：
   `E:\SteamLibrary\steamapps\common\sobosuba`
3. 如果修改器版未生成，点击 **「重新生成修改器版」**。
4. 点击 **「启动修改器版」**。
5. 进入游戏后：
   - **F2**：打开 / 关闭独立修改器窗口
   - **F3**：在鼠标位置生成球
   - **F1 / F4**：打开 / 关闭开发者控制台

如果还没有生成修改器版，启动器会提示并自动从原版生成。

启动器重新打包命令：

```bash
cd sobosuba-trainer
python -m PyInstaller --noconfirm --onefile --windowed --name SOBOSUBA修改器启动器 ^
  --icon "icons/sobosuba_mod.ico" ^
  --add-data "icons/sobosuba_mod.ico;." ^
  --add-data "icons/sobosuba_mod_small.png;." ^
  --paths "tools" --add-data "cheat.gd;." trainer_gui.py
```

---

## 内置菜单功能

| 分类 | 功能 |
|------|------|
| 分数 | 直接设置、+1000、+10000（会同步刷新分数显示） |
| 速度 | 0.25x / 0.5x / 1x / 2x / 4x 时间倍率（慢动作、加速） |
| 玩法 | 关闭重力、恢复重力、冻结危险挡板、关闭合并、冻结所有球、结束本局 |
| 解锁 | 解锁全部样式 / 成就 / 生成档位；本地排行榜 +100000、清空本地排行榜 |
| 球 | 按 F3 在鼠标位置生成指定等级球、清空所有球、修复所有球形状 |
| 存档 | 保存进度、读取进度、删除存档、清空成就、清空样式解锁 |
| 控制台 | 一键打开开发者控制台 |

---

## 控制台命令

按 **F1** 或 **F4** 打开控制台，输入命令后回车。常用命令：

```text
cheat_unlock_all             解锁全部样式、成就和生成档位
cheat_score_set 10000        设置当前分数
cheat_score_add 1000         当前分数增加 1000
cheat_time 0.5               时间倍率（0.5 = 慢动作）
cheat_spawn 8                在鼠标位置生成 8 级球
cheat_clear_sobos            清空所有球
cheat_gravity 0              关闭重力
cheat_freeze_bumpers true    冻结危险挡板
cheat_merging false          关闭合并
cheat_game_over              结束本局
```

游戏自带、同样可用的命令：

```text
unlock_all_styles            解锁全部样式
unlock_all_achievements      解锁全部成就
add_local_score 999999       本地排行榜添加分数
clear_local_scores           清空本地排行榜
clear_saved_game             删除当前局存档
start_game_mode mode_classic 切换游戏模式
debug_keys                   开启调试热键（S 生成球、X 删除球等）
list_all_commands            列出全部控制台命令
```

> 控制台中也可以用 `cheat_menu` 打开修改器面板。

---

## 重新生成修改器版

游戏更新后，修改器版仍然可以运行（它自带旧版游戏数据）。如果希望基于新版重新注入：

- 在本启动器中点击 **「重新生成修改器版」**；或
- 手动执行：

```bash
python tools/build_cheat.py --game "E:\SteamLibrary\steamapps\common\sobosuba\sobosuba.exe" --icon-png "icons/sobosuba_mod_small.png"
```

脚本会输出 `sobosuba.cheat.exe`，原版 exe 不受影响。

---

## 存档备份 / 恢复

启动器内置备份与恢复：

- **备份存档**：把 `achievements.dat`、`style_unlocks.dat`、`settings.tres`、`game_state.tres` 和自定义样式目录复制到 `backups/`；
- **恢复存档**：选择任意备份目录覆盖当前存档（请先关闭游戏）。

存档位置：

```text
%APPDATA%\Godot\app_userdata\sobosuba
```

---

## 技术原理

1. 读取原版 exe 末尾内嵌的 Godot PCK（Godot 4 的 `GDPC` 格式，版本 4）；
2. 在 `project.binary`（ECFG 配置格式）中追加：
   `autoload/Cheat = "*res://cheat.gd"`；
3. 把 `cheat.gd` 加入 PCK；
4. 重新打包并内嵌到 `sobosuba.cheat.exe`。

`cheat.gd` 是普通 GDScript 源码。Godot 正式版导出模板仍然支持运行时编译 `.gd` 源码，因此修改器以 autoload 形式运行，可以直接访问游戏中的：

- `ScoreManager`、`SignalBus`、`StyleManager`、`AchievementManager`
- `GameModeManager`、`SoboManager`、`Dev`、`Console`
- `GravityArea`、`Sobo` 等游戏对象

控制台原本在正式版中被禁用（`console.gdc` 里判断 `OS.has_feature("editor")` 后直接 `return`）。`cheat.gd` 在启动时会重新启用控制台并补上 `text_submitted` 信号连接，所以不需要修改原版脚本。

---

## 文件说明

| 文件 / 目录 | 说明 |
|-------------|------|
| `启动修改器.bat` | 双击打开启动器 |
| `trainer_gui.py` | 中文启动器（启动、重建、备份/恢复） |
| `cheat.gd` | 内置修改器脚本（F2 菜单 + 控制台命令） |
| `tools/build_cheat.py` | 从原版 exe 生成修改器版 |
| `tools/pck_tool.py` | Godot 4 PCK 解包 / 打包 / 内嵌工具 |
| `backups/` | 存档备份目录（自动创建） |

修改器版 exe 位于游戏目录：

```text
E:\SteamLibrary\steamapps\common\sobosuba\sobosuba.cheat.exe
```

---

## 常见问题

**Q：按 F2 没反应？**
A：确认启动的是 `sobosuba.cheat.exe`，不是原版。进入游戏窗口后先点一下游戏画面，再按 F2。

**Q：按 F1 / F4 控制台不出现？**
A：确保游戏窗口处于焦点状态。F1 是游戏自带的 `console_toggle` 动作，F4 是修改器额外提供的备用快捷键。

**Q：启动器提示“游戏正在运行”？**
A：重新生成或恢复存档前需要先关闭游戏（包括 `sobosuba.cheat.exe`），否则文件被占用。

**Q：demo 版能用吗？**
A：修改器按正式版构建。demo 是较早的构建，样式解锁接口不同，部分功能可能无效；请以正式版为准。

**Q：安全吗？**
A：修改器版是独立复制体，不改原版 exe、不联网注入、不修改系统文件。建议先备份存档再使用。

---

## 已验证环境

- Windows 11
- Godot Engine 4.7.2 stable（Steam 正式版）
- 原版位置：`E:\SteamLibrary\steamapps\common\sobosuba`
- 测试结果：F2 独立窗口菜单正常显示；28 个样式全部解锁成功；分数设置成功；控制台自动启用。
