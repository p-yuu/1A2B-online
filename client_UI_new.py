import socket
import threading
import time
import re
import queue
import flet as ft

# 預設連線資訊
DEFAULT_SERVER_IP = '127.0.0.1'
DEFAULT_SERVER_PORT = 5000

# 全域遊戲狀態
class GameState:
    def __init__(self):
        self.my_name = ""
        # 頁面狀態: ENTER_NAME, ROOM_CHOICE, CREATE_ROOM, JOIN_ROOM, LOBBY, SETTER_INPUT, GAME_PLAYING, MID_SCORE, FINAL_RANK
        self.page_state = "ENTER_NAME" 
        self.is_host = False
        self.room_id = ""
        self.answer_len = 4
        self.round_limit = 1
        self.room_players = []
        self.setter_name = ""
        self.is_setter = False
        self.current_guesser = ""
        self.guess_log = []          # 全體猜測實況紀錄
        self.personal_history = []  # 個人猜測歷史紀錄 (答題者專用)
        self.mid_scores = []         # 中場分數列表 [ (name, score), ... ]
        self.final_standings = []    # 最終排名列表 [ (name, score), ... ]
        self.system_notify = "等待遊戲開始..."
        self.last_round_msg = ""     # 回合結束通知
        self.chance_remaining = 10
        self.intent = ""             # "CREATE" 或 "JOIN" 意向
        self.error_message = ""      # 錯誤訊息提示
        
        # 本地輔助：答題者排除的數字 (0-9)
        self.excluded_digits = set()
        # 本地輔助：出題者當前輸入的數字
        self.setter_digits = []
        # 客戶端 UI 輸入狀態
        self.receive_buffer = ""
        self.name_input = ""
        self.room_id_input = ""
        self.guess_input = ""
        self.server_ip = DEFAULT_SERVER_IP
        self.server_port = str(DEFAULT_SERVER_PORT)

state = GameState()

# Socket 連線與執行緒控制
client_socket = None
running = True
page_ref = None  # 用於在背景執行緒中刷新 Flet 頁面

# Single source of truth event queue
event_queue = queue.Queue()
event_loop_started = False

def all_border(width, color):
    return ft.Border(
        top=ft.BorderSide(width, color),
        bottom=ft.BorderSide(width, color),
        left=ft.BorderSide(width, color),
        right=ft.BorderSide(width, color),
    )

def connect_to_server(ip, port):
    global client_socket, running
    try:
        if client_socket:
            try:
                client_socket.close()
            except:
                pass
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.connect((ip, int(port)))
        running = True
        return True, ""
    except Exception as e:
        return False, str(e)


def clean_and_restart():
    """重置局部房間遊戲狀態，保留姓名與 Socket"""
    self_name = state.my_name
    server_ip = state.server_ip
    server_port = state.server_port
    state.__init__()
    state.my_name = self_name
    state.server_ip = server_ip
    state.server_port = server_port
    state.page_state = "ROOM_CHOICE"


def send_to_server(command):
    global client_socket
    if not client_socket:
        return False, "尚未建立伺服器連線。"
    try:
        text = command if command.endswith("\n") else command + "\n"
        client_socket.send(text.encode())
        return True, ""
    except Exception as e:
        return False, str(e)


def dispatch(event):
    event_queue.put(event)


def event_loop():
    global event_loop_started
    if event_loop_started:
        return
    event_loop_started = True
    while running:
        try:
            event = event_queue.get(timeout=0.1)
        except queue.Empty:
            continue
        try:
            handle_event(event)
        except Exception as e:
            print(f"Event loop error: {e}")
        build_current_screen()
    safe_update()


def handle_server_raw(data):
    buffer = state.receive_buffer + data

    if "請輸入你的名字:" in buffer:
        state.page_state = "ENTER_NAME"
        buffer = buffer.replace("請輸入你的名字:", "")

    if "名字已被使用，請重新輸入" in buffer:
        state.error_message = "這個名字已經有人用了！請換一個。"
        state.page_state = "ENTER_NAME"
        buffer = buffer.replace("名字已被使用，請重新輸入", "")

    if "1. 創建房間" in buffer and "2. 加入房間" in buffer:
        state.page_state = "ROOM_CHOICE"
        state.error_message = ""
        buffer = buffer.replace("1. 創建房間", "")
        buffer = buffer.replace("2. 加入房間", "")

    if "請輸入房號:" in buffer:
        if state.intent == "CREATE":
            state.page_state = "CREATE_ROOM"
        elif state.intent == "JOIN":
            state.page_state = "JOIN_ROOM"
        buffer = buffer.replace("請輸入房號:", "")

    if "房號已存在，請重新輸入" in buffer:
        state.error_message = "房號已被佔用，請重新輸入"
        state.page_state = "CREATE_ROOM"
        buffer = buffer.replace("房號已存在，請重新輸入", "")

    if "房間不存在，請重新輸入" in buffer:
        state.error_message = "找不到這個房間，請重新確認房號"
        state.page_state = "JOIN_ROOM"
        buffer = buffer.replace("房間不存在，請重新輸入", "")

    if "請輸入密碼字數:" in buffer:
        success, err = send_to_server(str(state.answer_len))
        if not success:
            state.error_message = f"自動回覆密碼長度失敗：{err}"
        buffer = buffer.replace("請輸入密碼字數:", "")

    if "請輸入回合數:" in buffer:
        success, err = send_to_server(str(state.round_limit))
        if not success:
            state.error_message = f"自動回覆回合數失敗：{err}"
        buffer = buffer.replace("請輸入回合數:", "")

    m_create = re.search(r"房間\s*(\S+)\s*創建成功", buffer)
    if m_create:
        state.room_id = m_create.group(1)
        state.is_host = True
        state.page_state = "LOBBY"
        buffer = buffer.replace(m_create.group(0), "")

    if "=== 房間玩家 ===" in buffer:
        idx = buffer.find("=== 房間玩家 ===")
        sub = buffer[idx:]
        lines = [l.strip() for l in sub.split("\n") if l.strip()]
        players = []
        for l in lines[1:]:
            if l.startswith("===") or "創建成功" in l or "1." in l or "請輸入" in l:
                break
            players.append(l)
        if players:
            state.room_players = players
            if state.page_state in ["CREATE_ROOM", "JOIN_ROOM", "ROOM_CHOICE"]:
                state.page_state = "LOBBY"

    m_join = re.search(r"(\S+)\s*加入房間", buffer)
    if m_join:
        new_p = m_join.group(1)
        if new_p not in state.room_players:
            state.room_players.append(new_p)

    if "=== 新回合開始 ===" in buffer:
        state.guess_log = []
        state.personal_history = []
        state.excluded_digits = set()
        state.setter_digits = []
        state.chance_remaining = 10
        m_setter = re.search(r"目前出題者:\s*(\S+)", buffer)
        if m_setter:
            state.setter_name = m_setter.group(1)
            state.is_setter = (state.setter_name == state.my_name)
        state.page_state = "GAME_PLAYING"
        state.system_notify = f"新回合開始！出題者：{state.setter_name}"
        buffer = buffer.replace("=== 新回合開始 ===", "")

    if "位不重複數字作為答案:" in buffer:
        m_len = re.search(r"請輸入(\d+)位不重複數字作為答案", buffer)
        if m_len:
            state.answer_len = int(m_len.group(1))
        state.page_state = "SETTER_INPUT"
        state.is_setter = True
        state.setter_digits = []
        buffer = buffer.replace("位不重複數字作為答案:", "")

    if "答案已設定，開始猜題！" in buffer:
        state.page_state = "GAME_PLAYING"
        m_turn = re.search(r"【輪到玩家\s*(\S+)\s*作答】", buffer)
        if m_turn:
            state.current_guesser = m_turn.group(1)
            if state.current_guesser == state.my_name:
                state.system_notify = "🎉 輪到你猜題了！"
            else:
                state.system_notify = f"👤 等待 {state.current_guesser} 作答中"
        buffer = buffer.replace("答案已設定，開始猜題！", "")

    m_turn1 = re.search(r"【本輪作答玩家:\s*(\S+?)】", buffer)
    if m_turn1:
        state.current_guesser = m_turn1.group(1)
        if state.current_guesser == state.my_name:
            state.system_notify = "🎉 輪到你猜題了！"
        else:
            state.system_notify = f"等待 {state.current_guesser} 作答中"
        buffer = buffer.replace(m_turn1.group(0), "")

    m_turn2 = re.search(r"下一位作答玩家:\s*(\S+?)】", buffer)
    if m_turn2:
        state.current_guesser = m_turn2.group(1)
        if state.current_guesser == state.my_name:
            state.system_notify = "🎉 輪到你猜題了！"
        else:
            state.system_notify = f"等待 {state.current_guesser} 作答中"
        buffer = buffer.replace(m_turn2.group(0), "")

    m_g1 = re.findall(r"玩家\s*(\S+)\s*猜測\s*(\d+)\s*->?\s*(\d+A\d+B)", buffer)
    for item in m_g1:
        log_text = f"👤 {item[0]} 猜測 {item[1]} ➔ {item[2]}"
        if log_text not in state.guess_log:
            state.guess_log.append(log_text)

    m_g2 = re.findall(r"玩家\s*(\S+)\s*猜測結果\s*->?\s*(\d+A\d+B)", buffer)
    for item in m_g2:
        log_text = f"👤 {item[0]} ➔ {item[1]}"
        if log_text not in state.guess_log:
            state.guess_log.append(log_text)

    if "--- 你的個人猜測紀錄 ---" in buffer:
        idx_h = buffer.find("--- 你的個人猜測紀錄 ---")
        sub_h = buffer[idx_h:]
        lines_h = [l.strip() for l in sub_h.split("\n") if l.strip()]
        personal = []
        for l in lines_h[1:]:
            if l.startswith("===") or "玩家" in l or "輪到" in l or "請輸入" in l:
                break
            personal.append(l)
        if personal:
            state.personal_history = personal
        m_chance = re.search(r"剩餘猜測次數:\s*(\d+)\s*次", buffer)
        if m_chance:
            state.chance_remaining = int(m_chance.group(1))

    round_ended = False
    if "猜中了答案！本回合結束" in buffer:
        round_ended = True
        m_win = re.search(r"(\S+)\s*猜中了答案！本回合結束", buffer)
        if m_win:
            state.last_round_msg = f"🎉 恭喜！{m_win.group(1)} 猜中了正確答案！"
    elif "本回合無人猜中" in buffer:
        round_ended = True
        m_fail = re.search(r"本回合無人猜中。正確答案是:\s*(\S+)", buffer)
        if m_fail:
            state.last_round_msg = f"😢 殘念！本回合沒人猜中。\n正確答案是: {m_fail.group(1)}"

    if "=== 目前分數 ===" in buffer:
        idx_s = buffer.find("=== 目前分數 ===")
        sub_s = buffer[idx_s:]
        lines_s = [l.strip() for l in sub_s.split("\n") if l.strip()]
        scores = []
        for l in lines_s[1:]:
            if l.startswith("===") or "新回合" in l or "遊戲結束" in l:
                break
            parts = l.split(":")
            if len(parts) == 2:
                scores.append((parts[0].strip(), parts[1].replace("分", "").strip() + " 分"))
        state.mid_scores = scores
        state.page_state = "MID_SCORE"
        threading.Thread(target=mid_score_delay_transition, daemon=True).start()
        buffer = buffer.replace("=== 目前分數 ===", "")

    if "=== 最終排名 ===" in buffer:
        idx_f = buffer.find("=== 最終排名 ===")
        sub_f = buffer[idx_f:]
        lines_f = [l.strip() for l in sub_f.split("\n") if l.strip()]
        standings = []
        for l in lines_f[1:]:
            if "GAME_OVER_RESTART" in l:
                break
            parts = l.split(":")
            if len(parts) == 2:
                standings.append((parts[0].strip(), parts[1].replace("分", "").strip() + " 分"))
        state.final_standings = standings
        state.page_state = "FINAL_RANK"
        buffer = buffer.replace("=== 最終排名 ===", "")

    if "【系統警告】" in buffer:
        state.error_message = "系統警告：有玩家在對局中斷線！遊戲被迫終止。"
        state.page_state = "ROOM_CHOICE"
        buffer = buffer.replace("【系統警告】", "")

    if "GAME_OVER_RESTART" in buffer:
        time.sleep(0.5)
        send_to_server("QUIT_LOOP")
        buffer = buffer.replace("GAME_OVER_RESTART", "")

    state.receive_buffer = buffer


def handle_event(event):
    typ = event.get("type")
    payload = event.get("payload", {})

    if typ == "CONNECT_REQUEST":
        state.error_message = ""
        success, err = connect_to_server(payload.get("ip", state.server_ip), payload.get("port", state.server_port))
        if not success:
            state.error_message = f"無法連線到伺服器: {err}"
            return
        state.server_ip = payload.get("ip", state.server_ip)
        state.server_port = payload.get("port", state.server_port)
        state.name_input = payload.get("name", state.name_input)
        state.my_name = payload.get("name", state.my_name)
        state.system_notify = "已連線，等待伺服器回應..."
        threading.Thread(target=socket_receive_loop, daemon=True).start()
        send_success, send_err = send_to_server(state.my_name)
        if not send_success:
            state.error_message = f"發送名稱失敗：{send_err}"

    elif typ == "SET_NAME_INPUT":
        state.name_input = payload.get("value", "")

    elif typ == "SET_SERVER_IP":
        state.server_ip = payload.get("value", "")

    elif typ == "SET_SERVER_PORT":
        state.server_port = payload.get("value", "")

    elif typ == "SET_ROOM_ID_INPUT":
        state.room_id_input = payload.get("value", "")

    elif typ == "SET_ANSWER_LEN":
        state.answer_len = int(payload.get("value", state.answer_len))

    elif typ == "SET_ROUND_LIMIT":
        state.round_limit = int(payload.get("value", state.round_limit))

    elif typ == "CREATE_ROOM_SELECTED":
        state.intent = "CREATE"
        state.error_message = ""
        send_success, send_err = send_to_server("1")
        if not send_success:
            state.error_message = f"發送創建房間指令失敗：{send_err}"

    elif typ == "JOIN_ROOM_SELECTED":
        state.intent = "JOIN"
        state.error_message = ""
        send_success, send_err = send_to_server("2")
        if not send_success:
            state.error_message = f"發送加入房間指令失敗：{send_err}"

    elif typ == "SUBMIT_ROOM_ID":
        room_id = payload.get("room_id", "").strip()
        if not room_id:
            state.error_message = "房號不能為空！"
            return
        state.room_id_input = room_id
        state.room_id = room_id
        state.error_message = ""
        send_success, send_err = send_to_server(room_id)
        if not send_success:
            state.error_message = f"傳送房號失敗：{send_err}"

    elif typ == "START_GAME":
        send_success, send_err = send_to_server("start")
        if not send_success:
            state.error_message = f"傳送開始指令失敗：{send_err}"

    elif typ == "SETTER_DIGIT_PRESS":
        digit = payload.get("digit")
        if not digit:
            return
        if len(state.setter_digits) >= state.answer_len:
            return
        if digit in state.setter_digits:
            state.error_message = "密碼數字不能重複喔！"
            return
        state.setter_digits.append(digit)
        state.error_message = ""

    elif typ == "SETTER_DIGIT_BACKSPACE":
        if state.setter_digits:
            state.setter_digits.pop()
            state.error_message = ""

    elif typ == "SETTER_DIGIT_CLEAR":
        state.setter_digits.clear()
        state.error_message = ""

    elif typ == "SUBMIT_SECRET":
        if len(state.setter_digits) != state.answer_len:
            state.error_message = f"密碼長度必須是 {state.answer_len} 位數！"
            return
        secret = "".join(state.setter_digits)
        send_success, send_err = send_to_server(secret)
        if not send_success:
            state.error_message = f"發送答案失敗：{send_err}"
        else:
            state.error_message = ""

    elif typ == "SET_GUESS_INPUT":
        state.guess_input = payload.get("value", "")

    elif typ == "SUBMIT_GUESS":
        val = payload.get("guess", "").strip()
        if not val:
            return
        if len(val) != state.answer_len or not val.isdigit() or len(set(val)) != state.answer_len:
            state.error_message = f"格式錯誤，請輸入 {state.answer_len} 位不重複數字！"
            return
        send_success, send_err = send_to_server(val)
        if not send_success:
            state.error_message = f"傳送猜測失敗：{send_err}"
        else:
            state.guess_input = ""
            state.error_message = ""

    elif typ == "TOGGLE_DIGIT_EXCLUDE":
        digit = payload.get("digit")
        if digit in state.excluded_digits:
            state.excluded_digits.remove(digit)
        else:
            state.excluded_digits.add(digit)

    elif typ == "CLEAN_AND_RESTART":
        clean_and_restart()

    elif typ == "SET_ERROR_MESSAGE":
        state.error_message = payload.get("message", "")

    elif typ == "SERVER_RAW_DATA":
        handle_server_raw(payload.get("data", ""))

    elif typ == "SERVER_DISCONNECTED":
        state.error_message = "與伺服器斷開連線！"
        state.page_state = "ENTER_NAME"


def socket_receive_loop():
    """背景執行緒：負責接收伺服器訊息並解析成結構化狀態"""
    global running, client_socket

    while running:
        try:
            data = client_socket.recv(1024).decode()
            if not data:
                break
            print(f"[Server Raw]: {data}")
            dispatch({"type": "SERVER_RAW_DATA", "payload": {"data": data}})
        except Exception as e:
            print(f"Socket讀取錯誤: {e}")
            break

    dispatch({"type": "SERVER_DISCONNECTED"})


def mid_score_delay_transition():
    """中場停留5秒，倒數計時後平滑切回遊戲或出題畫面"""
    for i in range(5, 0, -1):
        if state.page_state != "MID_SCORE":
            return
        state.system_notify = f"即將進入下個回合... ({i}s)"
        safe_update()
        time.sleep(1)
        
    # 時間到，如果沒有跳到最終結算，就依據身分切換
    if state.page_state == "MID_SCORE":
        if state.is_setter:
            state.page_state = "SETTER_INPUT"
        else:
            state.page_state = "GAME_PLAYING"
        safe_update()

# ----------------------------------------------------
# Flet 介面設計
# ----------------------------------------------------

def main(page: ft.Page):
    global page_ref
    page_ref = page
    
    # 設置手機尺寸框架 (便於打包成.apk後在實體機流暢呈現)
    page.title = "1A2B 猜數字大對決"
    page.window.width = 410
    page.window.height = 820
    page.window.resizable = True
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 0
    page.margin = 0
    page.bgcolor = "#FCF8F5"  # 設計圖中的溫暖淺奶油色

    # 背景 Socket 關閉
    def on_close(e):
        global running, client_socket
        running = False
        if client_socket:
            try:
                client_socket.close()
            except:
                pass
    page.on_close = on_close

    # 主視窗結構
    global app_container
    app_container = ft.Column(
        alignment=ft.MainAxisAlignment.CENTER,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        expand=True
    )
    
    threading.Thread(target=event_loop, daemon=True).start()
    
    page.add(
        ft.Container(
            content=app_container,
            expand=True,
            gradient=ft.LinearGradient(
                begin=ft.alignment.Alignment(0, -1),
                end=ft.alignment.Alignment(0, 1),
                colors=["#FCF8F5", "#FEECE2"]
            )
        )
    )

    # 首次渲染
    build_current_screen()

def build_current_screen():
    """根據當前 state.page_state 完全重新渲染核心卡片，實現流暢的頁面轉場"""
    app_container.controls.clear()
    
    # 手機風格卡片容器
    card_content = None
    
    if state.page_state == "ENTER_NAME":
        card_content = render_enter_name()
    elif state.page_state == "ROOM_CHOICE":
        card_content = render_room_choice()
    elif state.page_state == "CREATE_ROOM":
        card_content = render_create_room()
    elif state.page_state == "JOIN_ROOM":
        card_content = render_join_room()
    elif state.page_state == "LOBBY":
        card_content = render_lobby()
    elif state.page_state == "SETTER_INPUT":
        card_content = render_setter_input()
    elif state.page_state == "GAME_PLAYING":
        card_content = render_game_playing()
    elif state.page_state == "MID_SCORE":
        card_content = render_mid_score()
    elif state.page_state == "FINAL_RANK":
        card_content = render_final_rank()
    
    # 統一的外層美觀圓角大卡片 (還原設計圖風格)
    mobile_frame = ft.Container(
        content=card_content,
        width=380,
        height=740,
        bgcolor="#FFFBF9",
        border_radius=30,
        padding=24,
        border=all_border(1.5, "#FCCEB4"),
        alignment=ft.Alignment.CENTER,
        shadow=ft.BoxShadow(
            blur_radius=15,
            color=ft.Colors.with_opacity(0.12, "#F98C53"),
            offset=ft.Offset(0, 6)
        )
    )
    
    app_container.controls.append(mobile_frame)
    page_ref.update()

# ----------------------------------------------------
# 1. 第一頁: 輸入名字 (ENTER_NAME)
# ----------------------------------------------------
def render_enter_name():
    name_field = ft.TextField(
        value=state.name_input,
        label="請輸入你的名字 Please input your name",
        label_style=ft.TextStyle(color="#2E221B", size=13),
        border_color="#F98C53",
        focused_border_color="#F98C53",
        cursor_color="#F98C53",
        border_radius=15,
        content_padding=15,
        bgcolor="white",
        text_align=ft.TextAlign.CENTER,
        on_change=lambda e: dispatch({"type": "SET_NAME_INPUT", "payload": {"value": e.control.value}}),
    )
    
    # 手機 APK 高可用：可編輯的 IP 與 Port 設定 (預設收摺)
    ip_field = ft.TextField(
        value=state.server_ip,
        label="伺服器 IP Address",
        border_color="#FCCEB4",
        border_radius=10,
        height=45,
        text_size=12,
        on_change=lambda e: dispatch({"type": "SET_SERVER_IP", "payload": {"value": e.control.value}}),
    )
    port_field = ft.TextField(
        value=state.server_port,
        label="Port",
        border_color="#FCCEB4",
        border_radius=10,
        height=45,
        text_size=12,
        on_change=lambda e: dispatch({"type": "SET_SERVER_PORT", "payload": {"value": e.control.value}}),
    )
    
    conn_settings = ft.ExpansionTile(
        title=ft.Text("連線進階設定 Server Settings", size=12, color="#2E221B"),
        controls_padding=10,
        controls=[
            ft.Row([ip_field, port_field], spacing=10)
        ]
    )

    err_text = ft.Text(state.error_message, color="red", size=12, weight="bold", text_align=ft.TextAlign.CENTER)

    def on_start_click(e):
        if not name_field.value.strip():
            dispatch({"type": "SET_ERROR_MESSAGE", "payload": {"message": "名字不能為空！"}})
            return
        dispatch({
            "type": "CONNECT_REQUEST",
            "payload": {
                "name": name_field.value.strip(),
                "ip": ip_field.value.strip(),
                "port": port_field.value.strip(),
            }
        })

    start_btn = ft.Button(
        content=ft.Text("START 開始"),
        bgcolor="#ABD7FB",
        color="#1A2D42",
        width=240,
        height=50,
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=15),
            elevation=3
        ),
        on_click=on_start_click
    )

    return ft.Column(
        controls=[
            ft.Container(height=20),
            # 頂部動態大 Title
            ft.Container(
                content=ft.Column([
                    ft.Text("ENTER NAME", size=26, weight="bold", color="#F98C53", style=ft.TextStyle(letter_spacing=2)),
                    ft.Text("1A2B 密碼大作戰", size=14, color="#7C6E65", weight="w500")
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                alignment=ft.Alignment.CENTER,
                margin=ft.Margin(bottom=30)
            ),
            ft.Image(
                src="https://raw.githubusercontent.com/google/material-design-icons/master/png/social/group/lg_fnl_share.png",
                width=100,
                height=100,
                color="#F98C53",
            ),
            ft.Container(height=20),
            name_field,
            ft.Container(height=10),
            conn_settings,
            ft.Container(height=15),
            err_text,
            ft.Container(expand=True),
            start_btn,
            ft.Container(height=20),
        ],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        expand=True
    )

# ----------------------------------------------------
# 2. 第二頁: 選擇房間模式 (ROOM_CHOICE)
# ----------------------------------------------------
def render_room_choice():
    # 頂部問候
    header = ft.Column(
        controls=[
            ft.Text("ROOM CHOICE", size=26, weight="bold", color="#F98C53", style=ft.TextStyle(letter_spacing=1.5)),
            ft.Text(f"哈囉, {state.my_name}! 準備好開始了嗎？", size=14, color="#7C6E65"),
        ],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        margin=ft.Margin(top=20, bottom=40)
    )

    def on_create_room(e):
        dispatch({"type": "CREATE_ROOM_SELECTED"})

    def on_join_room(e):
        dispatch({"type": "JOIN_ROOM_SELECTED"})

    create_btn = ft.Button(
        content=ft.Row([
             ft.Text("🏠", size=18),
            ft.Text("創建房間 CREATE", size=16, weight="bold", color="white")
        ], alignment=ft.MainAxisAlignment.CENTER),
        bgcolor="#F98C53",
        width=280,
        height=65,
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=18),
            elevation=4
        ),
        on_click=on_create_room
    )

    join_btn = ft.Button(
        content=ft.Row([
            ft.Text("🚪"),
            ft.Text("加入房間 JOIN", size=16, weight="bold", color="#3A4A1C")
        ], alignment=ft.MainAxisAlignment.CENTER),
        bgcolor="#D2E0AA",
        width=280,
        height=65,
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=18),
            elevation=4
        ),
        on_click=on_join_room
    )

    err_text = ft.Text(state.error_message, color="red", size=12, weight="bold", text_align=ft.TextAlign.CENTER)

    return ft.Column(
        controls=[
            header,
            ft.Container(height=40),
            ft.Container(
                content=ft.Column([
                    create_btn,
                    ft.Container(height=25),
                    join_btn,
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                alignment=ft.Alignment.CENTER
            ),
            ft.Container(height=20),
            err_text,
            ft.Container(expand=True),
            ft.Text("1A2B Multiplayer Engine v2.0", size=10, color="#CCCCCC"),
            ft.Container(height=10)
        ],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        expand=True
    )

# ----------------------------------------------------
# 3A. 創建房間頁面 (CREATE_ROOM)
# ----------------------------------------------------
def render_create_room():
    room_id_field = ft.TextField(
        value=state.room_id_input,
        label="自訂房號 Room ID",
        border_color="#F98C53",
        focused_border_color="#F98C53",
        border_radius=12,
        bgcolor="white",
        content_padding=15,
        on_change=lambda e: dispatch({"type": "SET_ROOM_ID_INPUT", "payload": {"value": e.control.value}}),
    )
    
    # 密碼字數下拉選單 (1~10，預設4)
    len_dropdown = ft.Dropdown(
        label="密碼位數 Password Length",
        border_color="#F98C53",
        border_radius=12,
        bgcolor="white",
        value=str(state.answer_len),
        options=[ft.dropdown.Option(str(i)) for i in range(1, 11)],
        on_select=lambda e: dispatch({"type": "SET_ANSWER_LEN", "payload": {"value": e.control.value}}),
    )

    # 回合數下拉選單 (1~10，預設1)
    round_dropdown = ft.Dropdown(
        label="遊戲回合數 Rounds",
        border_color="#F98C53",
        border_radius=12,
        bgcolor="white",
        value=str(state.round_limit),
        options=[ft.dropdown.Option(str(i)) for i in range(1, 11)],
        on_select=lambda e: dispatch({"type": "SET_ROUND_LIMIT", "payload": {"value": e.control.value}}),
    )

    err_text = ft.Text(state.error_message, color="red", size=12, weight="bold", text_align=ft.TextAlign.CENTER)

    def on_submit_create(e):
        dispatch({
            "type": "SUBMIT_ROOM_ID",
            "payload": {
                "room_id": room_id_field.value.strip()
            }
        })

    submit_btn = ft.Button(
        content=ft.Text("建立並進入房間"),
        bgcolor="#F98C53",
        color="white",
        width=260,
        height=50,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=15)),
        on_click=on_submit_create
    )

    return ft.Column(
        controls=[
            ft.Row([
                ft.IconButton(
                    icon=ft.icons.arrow_back_ios_rounded,
                    on_click=lambda _: dispatch({"type": "CLEAN_AND_RESTART"})
                ),
                ft.Text("CREATE ROOM 創建房間", size=20, weight="bold", color="#F98C53")
            ], alignment=ft.MainAxisAlignment.START),
            ft.Container(height=20),
            room_id_field,
            ft.Container(height=15),
            len_dropdown,
            ft.Container(height=15),
            round_dropdown,
            ft.Container(height=20),
            err_text,
            ft.Container(expand=True),
            submit_btn,
            ft.Container(height=20)
        ],
        expand=True
    )

# ----------------------------------------------------
# 3B. 加入房間頁面 (JOIN_ROOM)
# ----------------------------------------------------
def render_join_room():
    room_id_field = ft.TextField(
        value=state.room_id_input,
        label="請輸入房號 Please enter Room ID",
        border_color="#F98C53",
        focused_border_color="#F98C53",
        border_radius=12,
        bgcolor="white",
        content_padding=15,
        on_change=lambda e: dispatch({"type": "SET_ROOM_ID_INPUT", "payload": {"value": e.control.value}}),
    )

    err_text = ft.Text(state.error_message, color="red", size=12, weight="bold", text_align=ft.TextAlign.CENTER)

    def on_submit_join(e):
        dispatch({
            "type": "SUBMIT_ROOM_ID",
            "payload": {
                "room_id": room_id_field.value.strip()
            }
        })

    submit_btn = ft.Button(
        content=ft.Text("JOIN 加入"),
        bgcolor="#ABD7FB",
        color="#1A2D42",
        width=260,
        height=50,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=15)),
        on_click=on_submit_join
    )

    return ft.Column(
        controls=[
            ft.Row([
                ft.IconButton(
                    icon=ft.icons.arrow_back_ios_rounded,
                    on_click=lambda _: dispatch({"type": "CLEAN_AND_RESTART"})
                ),
                ft.Text("JOIN ROOM 加入房間", size=20, weight="bold", color="#F98C53")
            ], alignment=ft.MainAxisAlignment.START),
            ft.Container(height=40),
            room_id_field,
            ft.Container(height=20),
            err_text,
            ft.Container(expand=True),
            submit_btn,
            ft.Container(height=20)
        ],
        expand=True
    )

# ----------------------------------------------------
# 4. 遊戲大廳 (LOBBY)
# ----------------------------------------------------
def render_lobby():
    # 房主才能點擊開始遊戲，其他玩家顯示等待中
    host_control = None
    if state.is_host:
        def start_game_action(e):
            if len(state.room_players) < 2:
                dispatch({"type": "SET_ERROR_MESSAGE", "payload": {"message": "大廳人數不足！至少需要 2 位玩家。"}})
                return
            dispatch({"type": "START_GAME"})

        host_control = ft.Button(
            content=ft.Text("遊戲開始 START GAME"),
            bgcolor="#F98C53",
            color="white",
            width=260,
            height=50,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=15)),
            on_click=start_game_action
        )
    else:
        host_control = ft.Column([
            ft.ProgressRing(color="#F98C53", width=30, height=30),
            ft.Container(height=10),
            ft.Text("等待房主開始對局...", italic=True, color="#7C6E65", size=13)
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER)

    players_list_view = ft.ListView(expand=True, spacing=10)
    for p in state.room_players:
        badge = "👑 房主" if p == state.room_players[0] else "👤 玩家"
        players_list_view.controls.append(
            ft.Container(
                content=ft.Row([
                    ft.Text(f" {badge} ", color="#F98C53", size=11, weight="bold", bgcolor="#FFF0E6", border_radius=5),
                    ft.Text(p, size=15, weight="bold", color="#2E221B")
                ]),
                padding=12,
                bgcolor="#FCF8F5",
                border_radius=10,
                border=all_border(1, "#FCCEB4")
            )
        )

    return ft.Column(
        controls=[
            ft.Row([
                ft.IconButton(
                    icon=ft.icons.exit_to_app_rounded,
                    icon_color="red",
                    on_click=lambda _: dispatch({"type": "CLEAN_AND_RESTART"})
                ),
                ft.Text(f"房間 ➔ {state.room_id}", size=20, weight="bold", color="#F98C53")
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Container(height=10),
            ft.Text("=== 目前在大廳的玩家 ===", size=13, color="#7C6E65", weight="bold"),
            ft.Container(height=10),
            ft.Container(
                content=players_list_view,
                expand=True,
                bgcolor="white",
                border_radius=15,
                padding=15,
                border=all_border(1, "#FEECE2")
            ),
            ft.Container(height=15),
            ft.Text(state.error_message, color="red", size=12, weight="bold"),
            ft.Container(height=15),
            ft.Container(
                content=host_control,
                alignment=ft.Alignment.CENTER
            ),
            ft.Container(height=10)
        ],
        expand=True
    )

# ----------------------------------------------------
# 5. 出題者：輸入題目密碼 (SETTER_INPUT)
# ----------------------------------------------------
def render_setter_input():
    # 根據要求的密碼長度，顯示對應個數的密碼方框
    code_boxes = ft.Row(alignment=ft.MainAxisAlignment.CENTER, spacing=10)
    
    # 填充當前已輸入的位數
    for i in range(state.answer_len):
        digit = ""
        if i < len(state.setter_digits):
            digit = state.setter_digits[i]
            
        code_boxes.controls.append(
            ft.Container(
                content=ft.Text(digit, size=24, weight="bold", color="#2E221B"),
                width=50,
                height=60,
                bgcolor="#FFF0E6",
                border=all_border(2, "#F98C53"),
                border_radius=12,
                alignment=ft.Alignment.CENTER
            )
        )

    # 虛擬小鍵盤事件處理
    def on_num_key(num):
        dispatch({"type": "SETTER_DIGIT_PRESS", "payload": {"digit": num}})

    def on_backspace(e):
        dispatch({"type": "SETTER_DIGIT_BACKSPACE"})

    def on_clear(e):
        dispatch({"type": "SETTER_DIGIT_CLEAR"})

    # 設計虛擬數字小鍵盤
    keyboard_grid = ft.Column(spacing=10, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
    
    # 行 1-3 數字按鈕
    for r in range(3):
        row_controls = []
        for c in range(1, 4):
            val = str(r * 3 + c)
            row_controls.append(
                ft.Button(
                    content=ft.Text(val),
                    width=65,
                    height=50,
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10), bgcolor="white", color="#2E221B"),
                    on_click=lambda e, v=val: on_num_key(v)
                )
            )
        keyboard_grid.controls.append(ft.Row(row_controls, alignment=ft.MainAxisAlignment.CENTER, spacing=10))

    # 最後一行：清除、0、倒退
    keyboard_grid.controls.append(
        ft.Row([
            ft.Button(
                content=ft.Text("C"), width=65, height=50,
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10), bgcolor="#FEECE2", color="#F98C53"),
                on_click=on_clear
            ),
            ft.Button(
                content=ft.Text("0"), width=65, height=50,
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10), bgcolor="white", color="#2E221B"),
                on_click=lambda e: on_num_key("0")
            ),
            ft.IconButton(
                icon=ft.icons.backspace_rounded,
                icon_color="white",
                bgcolor="#F98C53",
                width=65,
                height=50,
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
                on_click=on_backspace
            )
        ], alignment=ft.MainAxisAlignment.CENTER, spacing=10)
    )

    # 確認出題發送
    def submit_code(e):
        dispatch({"type": "SUBMIT_SECRET"})

    send_btn = ft.Button(
        content=ft.Row([
            ft.Text("SET CODE 設定答案", size=15, weight="bold", color="white"),
            ft.Text("🔑")
        ], alignment=ft.MainAxisAlignment.CENTER),
        bgcolor="#F98C53",
        width=260,
        height=52,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=15)),
        on_click=submit_code,
        disabled=(len(state.setter_digits) != state.answer_len)
    )

    err_text = ft.Text(state.error_message, color="red", size=12, weight="bold")

    return ft.Column(
        controls=[
            ft.Container(
                content=ft.Column([
                    ft.Text("QUESTIONER", size=24, weight="bold", color="#F98C53"),
                    ft.Text("- Set Code -", size=14, color="#7C6E65")
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                alignment=ft.Alignment.CENTER,
                margin=ft.Margin(top=10, bottom=15)
            ),
            ft.Text(f"請設定 {state.answer_len} 位不重複的秘密密碼", size=13, color="#2E221B"),
            ft.Container(height=10),
            code_boxes,
            ft.Container(height=15),
            err_text,
            ft.Container(expand=True),
            keyboard_grid,
            ft.Container(expand=True),
            send_btn,
            ft.Container(height=10)
        ],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        expand=True
    )

# ----------------------------------------------------
# 6. 遊戲核心游玩頁：區分出題者(監看)與答題者(遊玩)
# ----------------------------------------------------
def render_game_playing():
    if state.is_setter:
        # ==========================================
        # 出題者畫面：QUESTIONER - Live Monitor (監看戰況)
        # ==========================================
        notify_box = ft.Container(
            content=ft.Column([
                ft.Text("系統通知 System Notification", size=12, color="#7C6E65", weight="bold"),
                ft.Text(state.system_notify, size=15, color="#2E221B", weight="bold"),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            bgcolor="#FFF0E6",
            border_radius=15,
            padding=15,
            border=all_border(1, "#FCCEB4"),
            width=320,
            alignment=ft.Alignment.CENTER
        )

        log_list_view = ft.ListView(expand=True, spacing=8)
        for log in reversed(state.guess_log):
            log_list_view.controls.append(
                ft.Container(
                    content=ft.Text(log, size=13, color="#2E221B", weight="w500"),
                    padding=10,
                    bgcolor="#FCF8F5",
                    border_radius=8,
                    border=all_border(0.8, "#FEECE2")
                )
            )

        return ft.Column(
            controls=[
                ft.Container(
                    content=ft.Column([
                        ft.Text("QUESTIONER", size=22, weight="bold", color="#F98C53"),
                        ft.Text("- Live Monitor -", size=13, color="#7C6E65")
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    alignment=ft.Alignment.CENTER,
                    margin=ft.Margin(top=10, bottom=15)
                ),
                notify_box,
                ft.Container(height=15),
                ft.Row([
                    ft.Text("🔑", size=18),
                    ft.Text("猜測實況 Guess Log", size=13, weight="bold", color="#7C6E65")
                ]),
                ft.Container(height=5),
                ft.Container(
                    content=log_list_view,
                    expand=True,
                    bgcolor="white",
                    border_radius=15,
                    padding=15,
                    border=all_border(1, "#FEECE2")
                ),
                ft.Container(height=20),
                ft.Text("你是本回合出題者，請密切監控答題實況！", size=11, color="#7C6E65", italic=True),
                ft.Container(height=10)
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            expand=True
        )

    else:
        # ==========================================
        # 答題者畫面：SOLVER / GUESSER (主動答題、消去數字按鈕)
        # ==========================================
        is_my_turn = (state.current_guesser == state.my_name)

        # 頂部系統狀態通知
        bg_color = "#E2F0D9" if is_my_turn else "#FCF8F5"
        border_color = "#A2D07F" if is_my_turn else "#CCCCCC"
        
        notify_box = ft.Container(
            content=ft.Column([
                ft.Text("系統通知 System Notification", size=11, color="#7C6E65", weight="bold"),
                ft.Text(
                    "【輪到你作答！YOUR TURN TO GUESS】" if is_my_turn else state.system_notify,
                    size=14,
                    color="#2E221B" if not is_my_turn else "#2E4A1C",
                    weight="bold"
                ),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            bgcolor=bg_color,
            border_radius=15,
            padding=12,
            border=all_border(1.5, border_color),
            width=320,
            alignment=ft.Alignment.CENTER
        )

        # 猜題歷史紀錄
        history_list_view = ft.ListView(expand=True, spacing=8)
        # 優先顯示最上面的資訊
        for hist in reversed(state.personal_history):
            history_list_view.controls.append(
                ft.Container(
                    content=ft.Row([
                        ft.Text("🔑", size=16),
                        ft.Text(hist, size=13, color="#2E221B", weight="bold")
                    ]),
                    padding=8,
                    bgcolor="#FFFBF9",
                    border_radius=8,
                    border=all_border(0.8, "#FCCEB4")
                )
            )

        # Exclude Numbers Grid: 輔助按鈕。點擊後灰色表示排除，輔助消去法。
        exclude_rows = ft.Column(spacing=8, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
        
        def toggle_exclude(digit_num):
            dispatch({"type": "TOGGLE_DIGIT_EXCLUDE", "payload": {"digit": digit_num}})

        # 生成 0~9 兩行按鈕
        for row_idx in range(2):
            row_buttons = []
            for col_idx in range(5):
                num_val = row_idx * 5 + col_idx
                is_ex = (num_val in state.excluded_digits)
                
                # 依據是否排除調整顏色
                btn_bg = "#E0E0E0" if is_ex else "#ABD7FB"
                btn_color = "#808080" if is_ex else "#1A2D42"
                text_decor = ft.TextDecoration.LINE_THROUGH if is_ex else ft.TextDecoration.NONE
                
                row_buttons.append(
                    ft.Container(
                        content=ft.Text(
                            str(num_val), 
                            color=btn_color, 
                            weight="bold", 
                            size=14, 
                            decoration=text_decor
                        ),
                        width=45,
                        height=42,
                        bgcolor=btn_bg,
                        border_radius=10,
                        alignment=ft.Alignment.CENTER,
                        on_click=lambda e, v=num_val: toggle_exclude(v),
                    )
                )
            exclude_rows.controls.append(ft.Row(row_buttons, alignment=ft.MainAxisAlignment.CENTER, spacing=8))

        # 下方輸入答案框
        guess_input_field = ft.TextField(
            value=state.guess_input,
            label="輸入你的答案 Enter your answer",
            border_color="#F98C53",
            focused_border_color="#F98C53",
            border_radius=12,
            height=50,
            text_size=14,
            expand=True,
            bgcolor="white",
            content_padding=10,
            disabled=not is_my_turn,
            keyboard_type=ft.KeyboardType.NUMBER,
            on_change=lambda e: dispatch({"type": "SET_GUESS_INPUT", "payload": {"value": e.control.value}}),
        )

        def submit_guess(e):
            dispatch({"type": "SUBMIT_GUESS", "payload": {"guess": guess_input_field.value.strip()}})

        send_action_btn = ft.IconButton(
            icon=ft.icons.send_rounded,
            icon_color="white",
            bgcolor="#F98C53",
            width=50,
            height=50,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=12)),
            on_click=submit_guess,
            disabled=not is_my_turn
        )

        err_text = ft.Text(state.error_message, color="red", size=11, weight="bold")

        return ft.Column(
            controls=[
                ft.Container(
                    content=ft.Column([
                        ft.Text("SOLVER / SOLVER", size=20, weight="bold", color="#F98C53"),
                        ft.Text(f"剩餘猜測次數: {state.chance_remaining} 次", size=11, color="#7C6E65", weight="bold")
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    alignment=ft.Alignment.CENTER,
                    margin=ft.Margin(top=5, bottom=10)
                ),
                notify_box,
                ft.Container(height=10),
                # 歷史猜測歷史欄
                ft.Row([
                    ft.Text("🔑", size=16),
                    ft.Text("歷史猜測記錄 Guess History", size=12, weight="bold", color="#7C6E65")
                ]),
                ft.Container(height=4),
                ft.Container(
                    content=history_list_view,
                    expand=True,
                    bgcolor="white",
                    border_radius=12,
                    padding=10,
                    border=all_border(1, "#FEECE2")
                ),
                ft.Container(height=10),
                # 排除按鈕區塊
                ft.Text("💡 點擊消去輔助按鈕 (0-9 記事本)", size=10, color="#7C6E65", weight="bold"),
                exclude_rows,
                ft.Container(height=10),
                err_text,
                ft.Container(height=2),
                ft.Row([
                    guess_input_field,
                    send_action_btn
                ], spacing=10),
                ft.Container(height=5)
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            expand=True
        )

# ----------------------------------------------------
# 7. 回合結束中場結算 (MID_SCORE)
# ----------------------------------------------------
def render_mid_score():
    # 當前回合勝者或結果大標題
    title_display = ft.Container(
        content=ft.Text(
            state.last_round_msg,
            size=15,
            weight="bold",
            color="#2E221B",
            text_align=ft.TextAlign.CENTER,
        ),
        bgcolor="#FFF0E6",
        border_radius=15,
        padding=15,
        border=all_border(1.5, "#FCCEB4"),
        width=320,
        alignment=ft.Alignment.CENTER
    )

    scores_rows = ft.Column(spacing=10, expand=True)
    for idx, item in enumerate(state.mid_scores):
        medal = "🥇" if idx == 0 else "🥈" if idx == 1 else "👤"
        scores_rows.controls.append(
            ft.Container(
                content=ft.Row([
                    ft.Text(f"{medal} {item[0]}", size=16, weight="bold", color="#2E221B"),
                    ft.Text(f"{item[1]}", size=16, weight="bold", color="#F98C53")
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                bgcolor="#FCF8F5",
                border_radius=10,
                padding=12,
                border=all_border(1, "#FEECE2")
            )
        )

    return ft.Column(
        controls=[
            ft.Container(height=15),
            ft.Text("MID-GAME SCORE", size=24, weight="bold", color="#F98C53", style=ft.TextStyle(letter_spacing=1.5)),
            ft.Container(height=20),
            title_display,
            ft.Container(height=25),
            ft.Row([
                ft.Text("🔑"),
                ft.Text("目前積分 Standings", size=14, weight="bold", color="#7C6E65")
            ], alignment=ft.MainAxisAlignment.CENTER),
            ft.Container(height=10),
            ft.Container(
                content=scores_rows,
                expand=True,
                bgcolor="white",
                border_radius=15,
                padding=15,
                border=all_border(1, "#FEECE2")
            ),
            ft.Container(height=20),
            # 倒數 5 秒圖標與文字
            ft.Row([
                ft.Text("🔑"),
                ft.Text(state.system_notify, size=14, color="#7C6E65", weight="bold")
            ], alignment=ft.MainAxisAlignment.CENTER),
            ft.Container(height=20)
        ],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        expand=True
    )

# ----------------------------------------------------
# 8. 最終勝負排名結算 (FINAL_RANK)
# ----------------------------------------------------
def render_final_rank():
    # 頂部大冠亞軍排名字體
    trophy_icon = ft.Image(
        src="https://raw.githubusercontent.com/google/material-design-icons/master/png/social/cake/lg_fnl_share.png",
        width=100,
        height=100,
        color="#F98C53"
    )
    
    standings_rows = ft.Column(spacing=12, expand=True)
    for idx, item in enumerate(state.final_standings):
        rank_medal = "👑 第 1 名" if idx == 0 else f"🥈 第 {idx+1} 名"
        rank_bg = "#FFF0E6" if idx == 0 else "#FCF8F5"
        
        standings_rows.controls.append(
            ft.Container(
                content=ft.Row([
                    ft.Text(f"{rank_medal}  {item[0]}", size=16, weight="bold", color="#2E221B"),
                    ft.Text(f"{item[1]}", size=16, weight="bold", color="#F98C53")
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                bgcolor=rank_bg,
                border_radius=12,
                padding=15,
                border=all_border(1.5, "#FCCEB4" if idx == 0 else "#FEECE2")
            )
        )

    def go_back_to_lobby(e):
        dispatch({"type": "CLEAN_AND_RESTART"})

    back_btn = ft.Button(
        content=ft.Text("回到主畫面 BACK TO LOBBY"),
        bgcolor="#F98C53",
        color="white",
        width=260,
        height=55,
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=15),
            elevation=3
        ),
        on_click=go_back_to_lobby
    )

    return ft.Column(
        controls=[
            ft.Container(height=10),
            ft.Text("FINAL RANKING", size=26, weight="bold", color="#F98C53", style=ft.TextStyle(letter_spacing=1.5)),
            ft.Text("✨ 本局遊戲最終排名結果 ✨", size=13, color="#7C6E65"),
            ft.Container(height=15),
            trophy_icon,
            ft.Container(height=15),
            ft.Container(
                content=standings_rows,
                expand=True,
                bgcolor="white",
                border_radius=15,
                padding=15,
                border=all_border(1, "#FEECE2")
            ),
            ft.Container(height=20),
            back_btn,
            ft.Container(height=20)
        ],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        expand=True
    )

# ----------------------------------------------------
# 程式啟動入口
# ----------------------------------------------------
if __name__ == "__main__":
    ft.run(main)