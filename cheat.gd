extends Node

# ============================================================
# SOBOSUBA 内置修改器（autoload）
# 通过修改后的 PCK 注入，按 F2 打开/关闭中文作弊菜单
# 按 F3 在鼠标位置生成球，按 F1 打开开发者控制台
# ============================================================

const PANEL_WIDTH := 380
const TIER_MAX := 13

var panel: PanelContainer
var cheat_window: Window
var status_label: Label
var score_input: LineEdit
var tier_spin: SpinBox
var time_label: Label
var selected_tier := 4
var original_gravity := -1.0


func _ready() -> void:
	# 在暂停/菜单界面也能响应
	process_mode = Node.PROCESS_MODE_ALWAYS
	_build_ui()
	_enable_console()
	_start_cmd_server()
	_set_window_icon()
	print("[SOBOSUBA 修改器] 已加载：F2 打开菜单，F3 生成球")


func _set_window_icon() -> void:
	# 设置游戏窗口/任务栏图标（小尺寸优化版 PNG 由构建工具写入 PCK）
	var icon_path := "res://sobosuba_mod_small.png"
	if not ResourceLoader.exists(icon_path):
		return
	var texture = load(icon_path)
	if texture is Texture2D:
		DisplayServer.set_icon((texture as Texture2D).get_image())


# ------------------------------------------------------------
# 控制台由正式版默认禁用；这里重新接线并注册自定义命令
# ------------------------------------------------------------
func _enable_console() -> void:
	if not is_instance_valid(Console):
		return
	Console.visible = true
	Console.set_process_input(true)
	var cmd_line: LineEdit = Console.command_line
	if cmd_line and not cmd_line.text_submitted.is_connected(Console.submit_command):
		cmd_line.text_submitted.connect(Console.submit_command)
	if Console.suggestions_text:
		Console.suggestions_text.scroll_active = false
	Console.add_commands(self)


# ------------------------------------------------------------
# 本地命令服务器：供独立修改器 EXE 通过 127.0.0.1 远程控制
# 仅监听本机回环地址，不对外网开放
# ------------------------------------------------------------
const CMD_PORT := 24680

var cmd_server: TCPServer
var cmd_clients: Array = []


func _start_cmd_server() -> void:
	cmd_server = TCPServer.new()
	var error := cmd_server.listen(CMD_PORT, "127.0.0.1")
	if error == OK:
		print("[SOBOSUBA 修改器] 本地命令端口 127.0.0.1:%d 已启动" % CMD_PORT)
	else:
		print("[SOBOSUBA 修改器] 本地命令端口启动失败：%s" % error)
		cmd_server = null


func _process(_delta: float) -> void:
	if cmd_server == null:
		return
	while cmd_server.is_connection_available():
		var peer := cmd_server.take_connection()
		if peer:
			cmd_clients.append({"peer": peer, "buffer": ""})
	for i in range(cmd_clients.size() - 1, -1, -1):
		var client: Dictionary = cmd_clients[i]
		var peer: StreamPeerTCP = client["peer"]
		peer.poll()
		if peer.get_status() != StreamPeerTCP.STATUS_CONNECTED:
			cmd_clients.remove_at(i)
			continue
		var available := peer.get_available_bytes()
		if available <= 0:
			continue
		var result: Array = peer.get_partial_data(available)
		if result[0] != OK:
			cmd_clients.remove_at(i)
			continue
		client["buffer"] += (result[1] as PackedByteArray).get_string_from_utf8()
		while "\n" in client["buffer"]:
			var newline: int = client["buffer"].find("\n")
			var line: String = client["buffer"].substr(0, newline).strip_edges()
			client["buffer"] = client["buffer"].substr(newline + 1)
			if not line.is_empty():
				var reply := _handle_tcp_command(line)
				peer.put_data((reply + "\n").to_utf8_buffer())


func _handle_tcp_command(line: String) -> String:
	var parts := line.split(" ", false)
	if parts.is_empty():
		return "ERR empty"
	var command := parts[0].to_lower()
	var args := parts.slice(1)
	match command:
		"ping":
			return "OK pong"
		"status":
			var score := -1
			if is_instance_valid(ScoreManager):
				score = ScoreManager.current_score
			return "OK score=%d time=%.2f" % [score, Engine.time_scale]
		"score_set":
			if args.size() < 1:
				return "ERR args"
			set_score(_parse_int(args[0], 0))
			return "OK"
		"score_add":
			if args.size() < 1:
				return "ERR args"
			add_score(_parse_int(args[0], 0))
			return "OK"
		"time":
			if args.size() < 1:
				return "ERR args"
			set_time_scale(_parse_float(args[0], 1.0))
			return "OK"
		"unlock_all":
			unlock_all()
			return "OK"
		"spawn":
			var tier := _parse_int(args[0], 4) if args.size() > 0 else 4
			return "OK" if spawn_at_center(tier) else "ERR no_game"
		"clear_sobos":
			clear_sobos()
			return "OK"
		"gravity":
			if args.size() < 1:
				return "ERR args"
			set_gravity(_parse_float(args[0], 0.0))
			return "OK"
		"gravity_restore":
			restore_gravity()
			return "OK"
		"freeze_bumpers":
			freeze_bumpers(_parse_bool(args[0]) if args.size() > 0 else true)
			return "OK"
		"merging":
			set_merging(_parse_bool(args[0]) if args.size() > 0 else true)
			return "OK"
		"freeze_all":
			freeze_all_sobos(_parse_bool(args[0]) if args.size() > 0 else true)
			return "OK"
		"game_over":
			_game_over()
			return "OK"
		"save":
			return _tcp_save()
		"load":
			return _tcp_load()
		"delete_save":
			return _tcp_delete_save()
		"console_open":
			if is_instance_valid(Console):
				Console.open()
				return "OK"
			return "ERR no_console"
		"console_close":
			if is_instance_valid(Console):
				Console.close()
				return "OK"
			return "ERR no_console"
		"quit":
			get_tree().quit()
			return "OK"
		"help":
			return "OK score_set score_add time unlock_all spawn clear_sobos gravity gravity_restore freeze_bumpers merging freeze_all game_over save load delete_save console_open console_close status quit"
		_:
			return "ERR unknown"


func _parse_int(text: String, fallback: int) -> int:
	return int(text) if text.is_valid_int() else fallback


func _parse_float(text: String, fallback: float) -> float:
	return float(text) if text.is_valid_float() else fallback


func _parse_bool(text: String) -> bool:
	return text.to_lower() in ["1", "true", "yes", "on"]


func spawn_at_center(size_tier: int) -> bool:
	if not current_mode() or not is_instance_valid(Dev):
		return false
	var viewport := get_viewport()
	var screen_size := viewport.get_visible_rect().size
	var screen_pos := Vector2(screen_size.x * 0.5, screen_size.y * 0.28)
	var world_pos: Vector2 = Dev.get_canvas_transform().affine_inverse() * screen_pos
	Dev.dev_spawn(size_tier, world_pos)
	_status("已在场地中央生成 %d 级球" % size_tier)
	return true


func _tcp_save() -> String:
	var manager := _save_manager()
	if manager:
		manager.save()
		return "OK"
	return "ERR no_save_manager"


func _tcp_load() -> String:
	var manager := _save_manager()
	if manager:
		manager.load()
		return "OK"
	return "ERR no_save_manager"


func _tcp_delete_save() -> String:
	var manager := _save_manager()
	if manager:
		manager.delete()
		return "OK"
	return "ERR no_save_manager"


# ------------------------------------------------------------
# 界面
# ------------------------------------------------------------
func _build_ui() -> void:
	# 关闭子窗口嵌入，让修改器菜单成为独立的系统窗口
	if get_tree() and get_tree().root:
		get_tree().root.gui_embed_subwindows = false

	cheat_window = Window.new()
	cheat_window.title = "SOBOSUBA 修改器"
	cheat_window.size = Vector2i(400, 760)
	cheat_window.min_size = Vector2i(360, 520)
	cheat_window.visible = false
	cheat_window.always_on_top = true
	cheat_window.process_mode = Node.PROCESS_MODE_ALWAYS
	cheat_window.close_requested.connect(_hide_panel)
	add_child(cheat_window)

	var main_pos := DisplayServer.window_get_position()
	var main_size := DisplayServer.window_get_size()
	cheat_window.position = Vector2i(
		main_pos.x + maxi(0, main_size.x - 420),
		main_pos.y + 40
	)

	panel = PanelContainer.new()
	panel.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	cheat_window.add_child(panel)

	var panel_style := StyleBoxFlat.new()
	panel_style.bg_color = Color(0.03, 0.05, 0.08, 0.95)
	panel_style.border_color = Color(0.25, 0.75, 0.85, 0.9)
	panel_style.set_border_width_all(2)
	panel_style.set_corner_radius_all(10)
	panel_style.set_content_margin_all(12)
	panel.add_theme_stylebox_override("panel", panel_style)

	var menu_theme := _make_theme()
	if menu_theme:
		panel.theme = menu_theme

	var margin := MarginContainer.new()
	margin.add_theme_constant_override("margin_left", 8)
	margin.add_theme_constant_override("margin_right", 8)
	margin.add_theme_constant_override("margin_top", 8)
	margin.add_theme_constant_override("margin_bottom", 8)
	panel.add_child(margin)

	var root := VBoxContainer.new()
	root.add_theme_constant_override("separation", 8)
	margin.add_child(root)

	# 标题栏
	var title_row := HBoxContainer.new()
	var title := Label.new()
	title.text = "SOBOSUBA 修改器"
	title.add_theme_font_size_override("font_size", 22)
	title.add_theme_color_override("font_color", Color(0.55, 0.95, 1.0))
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title_row.add_child(title)
	var close_btn := Button.new()
	close_btn.text = "×"
	close_btn.custom_minimum_size = Vector2(36, 36)
	close_btn.pressed.connect(_toggle_panel)
	title_row.add_child(close_btn)
	root.add_child(title_row)

	var hint := Label.new()
	hint.text = "F2 开关菜单 · F3 生成球 · F1 / F4 控制台"
	hint.add_theme_color_override("font_color", Color(0.65, 0.72, 0.8))
	root.add_child(hint)

	# 可滚动内容区
	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	root.add_child(scroll)

	var box := VBoxContainer.new()
	box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	box.add_theme_constant_override("separation", 6)
	scroll.add_child(box)

	# 分数
	box.add_child(_section("分数"))
	var score_row := HBoxContainer.new()
	score_input = LineEdit.new()
	score_input.placeholder_text = "输入分数"
	score_input.text = "10000"
	score_input.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	score_input.text_submitted.connect(func(_text: String) -> void: _on_set_score())
	score_row.add_child(score_input)
	var set_score_btn := _button("设置")
	set_score_btn.pressed.connect(_on_set_score)
	score_row.add_child(set_score_btn)
	box.add_child(score_row)

	var score_row2 := HBoxContainer.new()
	score_row2.add_child(_button("分数 +1000", func() -> void: add_score(1000)))
	score_row2.add_child(_button("分数 +10000", func() -> void: add_score(10000)))
	box.add_child(score_row2)

	# 速度
	box.add_child(_section("速度"))
	var speed_row := HBoxContainer.new()
	for scale_value: float in [0.25, 0.5, 1.0, 2.0, 4.0]:
		var speed_btn := _button("%sx" % scale_value)
		speed_btn.pressed.connect(_on_speed_pressed.bind(scale_value))
		speed_row.add_child(speed_btn)
	box.add_child(speed_row)
	time_label = Label.new()
	time_label.text = "当前时间倍率：1.0x"
	box.add_child(time_label)

	# 玩法
	box.add_child(_section("玩法"))
	var gravity_row := HBoxContainer.new()
	gravity_row.add_child(_button("关闭重力", func() -> void: set_gravity(0.0)))
	gravity_row.add_child(_button("恢复重力", restore_gravity))
	box.add_child(gravity_row)

	var bumper_row := HBoxContainer.new()
	bumper_row.add_child(_button("冻结危险挡板", func() -> void: freeze_bumpers(true)))
	bumper_row.add_child(_button("解除挡板冻结", func() -> void: freeze_bumpers(false)))
	box.add_child(bumper_row)

	var merge_row := HBoxContainer.new()
	merge_row.add_child(_button("关闭合并", func() -> void: set_merging(false)))
	merge_row.add_child(_button("开启合并", func() -> void: set_merging(true)))
	box.add_child(merge_row)

	var frozen_row := HBoxContainer.new()
	frozen_row.add_child(_button("冻结所有球", func() -> void: freeze_all_sobos(true)))
	frozen_row.add_child(_button("解冻所有球", func() -> void: freeze_all_sobos(false)))
	box.add_child(frozen_row)

	box.add_child(_button("结束本局", _game_over))

	# 解锁
	box.add_child(_section("解锁"))
	box.add_child(_button("解锁全部样式 + 成就 + 生成档位", unlock_all))

	var unlock_row := HBoxContainer.new()
	unlock_row.add_child(_button("本地排行榜 +100000", func() -> void: add_local_score(100000)))
	unlock_row.add_child(_button("清空本地排行榜", clear_local_scores))
	box.add_child(unlock_row)

	# 球
	box.add_child(_section("球"))
	var spawn_row := HBoxContainer.new()
	var tier_label := Label.new()
	tier_label.text = "等级"
	spawn_row.add_child(tier_label)
	tier_spin = SpinBox.new()
	tier_spin.min_value = 0
	tier_spin.max_value = TIER_MAX
	tier_spin.value = selected_tier
	tier_spin.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	spawn_row.add_child(tier_spin)
	var spawn_btn := _button("F3 在鼠标处生成")
	spawn_btn.pressed.connect(func() -> void: spawn_at_mouse(int(tier_spin.value)))
	spawn_row.add_child(spawn_btn)
	box.add_child(spawn_row)

	var ball_row := HBoxContainer.new()
	ball_row.add_child(_button("清空所有球", clear_sobos))
	ball_row.add_child(_button("修复所有球", fix_all_sobos))
	box.add_child(ball_row)

	# 存档
	box.add_child(_section("存档"))
	var save_row := HBoxContainer.new()
	save_row.add_child(_button("保存进度", _save_state))
	save_row.add_child(_button("读取进度", _load_state))
	save_row.add_child(_button("删除存档", _delete_save))
	box.add_child(save_row)

	var clear_row := HBoxContainer.new()
	clear_row.add_child(_button("清空成就", clear_achievements))
	clear_row.add_child(_button("清空样式解锁", clear_style_unlocks))
	box.add_child(clear_row)

	# 控制台
	box.add_child(_section("控制台"))
	box.add_child(_button("打开开发者控制台（F1）", open_console))

	status_label = Label.new()
	status_label.text = "就绪"
	status_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	status_label.add_theme_color_override("font_color", Color(0.6, 0.95, 0.75))
	root.add_child(status_label)


func _make_theme() -> Theme:
	var menu_theme := Theme.new()
	menu_theme.default_font_size = 18
	var language_code := "zh_CN"
	if is_instance_valid(SettingsManager) and SettingsManager.settings:
		if SettingsManager.settings.language != "":
			language_code = SettingsManager.settings.language
	# 依次尝试当前语言、简中、英文；demo 没有语言资源时使用默认字体
	for code: String in [language_code, "zh_CN", "en"]:
		var path := "res://localization/language_%s.tres" % code
		if not ResourceLoader.exists(path):
			continue
		var language_res := load(path)
		if language_res and language_res.get("font") != null:
			menu_theme.default_font = language_res.get("font")
			break
	return menu_theme


func _section(text: String) -> Label:
	var label := Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size", 17)
	label.add_theme_color_override("font_color", Color(0.35, 0.85, 0.95))
	return label


func _button(text: String, callback: Callable = Callable()) -> Button:
	var button := Button.new()
	button.text = text
	button.custom_minimum_size = Vector2(0, 34)
	button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	if callback.is_valid():
		button.pressed.connect(callback)
	return button


func _status(text: String) -> void:
	if status_label:
		status_label.text = text


func _input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		if event.keycode == KEY_F2:
			_toggle_panel()
			get_viewport().set_input_as_handled()
		elif event.keycode == KEY_F3:
			# 控制台输入时不触发，避免误操作
			if is_instance_valid(Console) and Console.is_open():
				return
			spawn_at_mouse(int(tier_spin.value) if tier_spin else selected_tier)
			get_viewport().set_input_as_handled()
		elif event.keycode == KEY_F4:
			# 备用控制台快捷键，不依赖 Console 的输入映射
			if is_instance_valid(Console):
				if Console.is_open():
					Console.close()
				else:
					Console.open()
				get_viewport().set_input_as_handled()


func _toggle_panel() -> void:
	if cheat_window:
		cheat_window.visible = not cheat_window.visible
		if cheat_window.visible:
			cheat_window.grab_focus()


func _hide_panel() -> void:
	if cheat_window:
		cheat_window.hide()


# ------------------------------------------------------------
# 作弊功能
# ------------------------------------------------------------
func _on_set_score() -> void:
	if score_input == null:
		return
	var text := score_input.text.strip_edges()
	if not text.is_valid_int():
		_status("请输入有效的整数分数")
		return
	set_score(int(text))


func _on_speed_pressed(scale_value: float) -> void:
	set_time_scale(scale_value)


func set_score(value: int) -> void:
	if not is_instance_valid(ScoreManager):
		return
	# 开发者作弊会让 ScoreManager 禁用计分，这里恢复
	ScoreManager.disable_scoring = false
	ScoreManager.set_score(value)
	# 触发 UI 刷新（gain_score(0) 不会改变分数）
	SignalBus.on_gain_score.emit(0)
	_status("分数已设为 %d" % value)


func add_score(amount: int) -> void:
	if not is_instance_valid(ScoreManager):
		return
	ScoreManager.disable_scoring = false
	SignalBus.on_gain_score.emit(amount)
	_status("分数 +%d" % amount)


func set_time_scale(scale_value: float) -> void:
	Engine.time_scale = scale_value
	if time_label:
		time_label.text = "当前时间倍率：%sx" % scale_value
	_status("时间倍率已设为 %sx" % scale_value)


func current_mode():
	return GameModeManager.current_mode if is_instance_valid(GameModeManager) else null


var gravity_cache: Node = null


func _find_gravity_area() -> Node:
	if is_instance_valid(gravity_cache):
		return gravity_cache
	gravity_cache = _find_node_by_script(get_tree().root, "gravity_area.gdc")
	return gravity_cache


func _find_node_by_script(node: Node, script_file: String) -> Node:
	var script_res = node.get_script()
	if script_res and str(script_res.resource_path).ends_with(script_file):
		return node
	for child in node.get_children():
		var found := _find_node_by_script(child, script_file)
		if found:
			return found
	return null


func set_gravity(value: float) -> void:
	var gravity_area := _find_gravity_area()
	if not is_instance_valid(gravity_area):
		_status("请先开始一局游戏")
		return
	if original_gravity < 0.0:
		original_gravity = gravity_area.gravity
	gravity_area.gravity = value
	_status("重力已设为 %.1f" % value)


func restore_gravity() -> void:
	var gravity_area := _find_gravity_area()
	if original_gravity >= 0.0 and is_instance_valid(gravity_area):
		gravity_area.gravity = original_gravity
		_status("重力已恢复为 %.1f" % original_gravity)


func freeze_bumpers(enabled: bool) -> void:
	var mode = current_mode()
	var left = mode.get("left") if mode else null
	var right = mode.get("right") if mode else null
	if left and right:
		left.danger_bumper.rigidbody.freeze = enabled
		right.danger_bumper.rigidbody.freeze = enabled
		_status("危险挡板已%s" % ("冻结" if enabled else "解冻"))
	else:
		_status("请先开始经典模式")


func set_merging(enabled: bool) -> void:
	Dev.merging_enabled = enabled
	_status("合并已%s" % ("开启" if enabled else "关闭"))


func freeze_all_sobos(enabled: bool) -> void:
	if not is_instance_valid(SoboManager):
		return
	for sobo in SoboManager.all_sobos.duplicate():
		if is_instance_valid(sobo):
			sobo.freeze(enabled)
	_status("所有球已%s" % ("冻结" if enabled else "解冻"))


func unlock_all() -> void:
	if is_instance_valid(StyleManager):
		for style in StyleManager.styles:
			StyleManager.unlock_style(style)
	if is_instance_valid(AchievementManager):
		for def in AchievementManager.achievements:
			AchievementManager.unlock(def.id)
	var mode = current_mode()
	if mode and mode.spawn_pool:
		mode.spawn_pool.unlock_all_size_tiers()
	_status("已解锁全部样式、成就和生成档位")


func add_local_score(value: int) -> void:
	if is_instance_valid(ScoreManager):
		ScoreManager.add_local_score(value)
		_status("本地排行榜已添加 %d" % value)


func clear_local_scores() -> void:
	if is_instance_valid(ScoreManager):
		ScoreManager.clear_local_scores()
		_status("本地排行榜已清空")


func spawn_at_mouse(size_tier: int) -> void:
	selected_tier = size_tier
	if not current_mode():
		_status("请先开始一局游戏")
		return
	if not is_instance_valid(Dev):
		_status("开发者节点不可用")
		return
	Dev.dev_spawn(size_tier, Dev.get_global_mouse_position())
	_status("已在鼠标位置生成 %d 级球" % size_tier)


func clear_sobos() -> void:
	if is_instance_valid(SoboManager):
		SoboManager.free_all()
		_status("已清空所有球")


func fix_all_sobos() -> void:
	if is_instance_valid(SoboManager):
		for sobo in SoboManager.all_sobos.duplicate():
			if is_instance_valid(sobo):
				sobo.fix_shape()
		_status("已修复所有球")


func _game_over() -> void:
	if current_mode():
		SignalBus.on_game_over.emit()
		_status("已结束本局")
	else:
		_status("请先开始一局游戏")


func _save_manager() -> Node:
	return get_node_or_null("/root/SaveLoadManager")


func _save_state() -> void:
	var save_manager := _save_manager()
	if save_manager:
		save_manager.save()
		_status("已保存当前进度")
	else:
		_status("当前版本没有存档管理器")


func _load_state() -> void:
	var save_manager := _save_manager()
	if save_manager:
		save_manager.load()
		_status("已读取存档")
	else:
		_status("当前版本没有存档管理器")


func _delete_save() -> void:
	var save_manager := _save_manager()
	if save_manager:
		save_manager.delete()
		_status("已删除存档")
	else:
		_status("当前版本没有存档管理器")


func clear_achievements() -> void:
	if is_instance_valid(AchievementManager):
		AchievementManager.clear_achievements_cmd()
		_status("已清空成就")


func clear_style_unlocks() -> void:
	if is_instance_valid(StyleManager):
		StyleManager.clear_style_unlocks_cmd()
		_status("已清空样式解锁")


func open_console() -> void:
	if is_instance_valid(Console):
		Console.open()


# ------------------------------------------------------------
# 控制台命令（在 F1 控制台中输入）
# ------------------------------------------------------------
func cheat_menu_cmd() -> void:
	_toggle_panel()


func cheat_score_set_cmd(value: int) -> void:
	set_score(value)


func cheat_score_add_cmd(value: int) -> void:
	add_score(value)


func cheat_time_cmd(scale_value: float) -> void:
	set_time_scale(scale_value)


func cheat_unlock_all_cmd() -> void:
	unlock_all()


func cheat_spawn_cmd(size_tier: int) -> void:
	spawn_at_mouse(size_tier)


func cheat_clear_sobos_cmd() -> void:
	clear_sobos()


func cheat_gravity_cmd(value: float) -> void:
	set_gravity(value)


func cheat_freeze_bumpers_cmd(enabled: bool) -> void:
	freeze_bumpers(enabled)


func cheat_merging_cmd(enabled: bool) -> void:
	set_merging(enabled)


func cheat_game_over_cmd() -> void:
	_game_over()
