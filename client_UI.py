import socket
import threading
import time
import flet as ft

SERVER_IP = '127.0.0.1'  # 實際 Demo 時請記得改成 Server 電腦的區網 IP
SERVER_PORT = 5000

# 建立 TCP Socket 連線
client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect((SERVER_IP, SERVER_PORT))

running = True
current_stage = ""  # 用來儲存當前介面狀態，防止背景瘋狂刷新輸入框

def main(page: ft.Page):
    global running, current_stage

    # ----------------------------------------------------
    #  UI 核心配色與風格設定 (根據你的色卡)
    # ----------------------------------------------------
    COLOR_BG = "#F9F2EF"        # 柔和的米白底色
    COLOR_ORANGE = "#F98C53"    # 活力橘 (主要按鈕、房主)
    COLOR_GREEN = "#D2E0AA"     # 草綠色 (加入房間、答題成功)
    COLOR_BLUE = "#ABD7FB"      # 水藍色 (開始、加入按鈕)
    COLOR_PEACH = "#FCCEB4"     # 淺桃色 (卡片背景)
    COLOR_TEXT = "#2C2C2C"      # 深灰色高質感文字
    COLOR_GRAY = "#9E9E9E"      # 標記按鈕被點擊後的灰色
    
    page.title = "1A2B online"
    page.bgcolor = COLOR_BG
    page.window.width = 410
    page.window.height = 820
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.vertical_alignment = ft.MainAxisAlignment.START
    page.scroll = ft.ScrollMode.AUTO

    # ----------------------------------------------------
    #  全域狀態變數與 UI 元件初始化
    # ----------------------------------------------------
    view_container = ft.Container(expand=True)
    system_notification = ft.Text("系統通知", size=18, weight=ft.FontWeight.BOLD, color=COLOR_TEXT)
    guess_log_view = ft.ListView(expand=True, spacing=5, auto_scroll=True)

    # ----------------------------------------------------
    #  網路傳送橋樑
    # ----------------------------------------------------
    def submit_action(value_str):
        clean_value = value_str.strip() if value_str else ""
        if clean_value:
            try:
                client.send(clean_value.encode())
                print(f"Sent: {clean_value}")
            except Exception as e:
                print(f"Send error: {e}")

    # ----------------------------------------------------
    #  介面切換工廠 (根據 Server 傳來的文字動態渲染對應設計圖畫面)
    # ----------------------------------------------------
    def render_screen(mode, title_text, hint_text="", show_num_pads=False):
        global current_stage
        current_stage = mode  # 更新目前全域狀態
        view_container.content = None
        
        # 建立專屬輸入框
        current_input = ft.TextField(
            bgcolor="white", 
            color=COLOR_TEXT, 
            border_radius=10, 
            border_color=COLOR_ORANGE,
            text_align=ft.TextAlign.CENTER,
            text_size=16
        )
        
        # 重新綁定 Enter 送出事件：安全清空
        def on_input_submit(e):
            val = current_input.value
            current_input.value = ""
            try:
                current_input.update()
            except:
                pass  # 如果此時已經被背景切換畫面，直接安全跳過 update
            submit_action(val)
            
        current_input.on_submit = on_input_submit
        
        # 綁定按鈕點擊事件：安全清空
        def on_btn_click(e):
            val = current_input.value
            current_input.value = ""
            try:
                current_input.update()
            except:
                pass
            submit_action(val)
        
        # 標題與提示
        elements = [
            ft.Text(title_text, size=24, weight=ft.FontWeight.BOLD, color=COLOR_TEXT, text_align=ft.TextAlign.CENTER),
            ft.Text(hint_text, size=14, color=COLOR_TEXT, text_align=ft.TextAlign.CENTER) if hint_text else ft.Container()
        ]
        
        # 答題者專用：0~9 數字排記標籤按鈕
        if show_num_pads:
            grid_controls = []
            for i in range(10):
                btn_closed = [False]
                def make_click_cb(b, bc):
                    def pad_click(e):
                        b[0] = not b[0]
                        e.control.bgcolor = COLOR_GRAY if b[0] else COLOR_BLUE
                        e.control.update()
                    return pad_click
                
                grid_controls.append(
                    ft.Container(
                        content=ft.Text(str(i), color=COLOR_TEXT, weight=ft.FontWeight.BOLD),
                        alignment=ft.alignment.center,
                        bgcolor=COLOR_BLUE,
                        border_radius=8,
                        on_click=make_click_cb(btn_closed, i),
                        width=40,
                        height=40
                    )
                )
            
            num_pad_row1 = ft.Row(controls=grid_controls[:5], alignment=ft.MainAxisAlignment.CENTER, spacing=10)
            num_pad_row2 = ft.Row(controls=grid_controls[5:], alignment=ft.MainAxisAlignment.CENTER, spacing=10)
            elements.append(ft.Container(content=ft.Column([num_pad_row1, num_pad_row2]), margin=ft.margin.only(top=10, bottom=10)))

        # 根據模式組裝控制元件
        if mode == "ENTER_NAME":
            current_input.hint_text = "請輸入名字"
            current_input.label = "Name"
            elements.extend([
                current_input,
                ft.Button(
                    "開始 START", 
                    color=COLOR_TEXT, 
                    width=200,
                    style=ft.ButtonStyle(bgcolor=COLOR_BLUE, shape=ft.RoundedRectangleBorder(radius=10)),
                    on_click=on_btn_click
                )
            ])
            
        elif mode == "ROOM_CHOICE":
            elements.extend([
                ft.Button(
                    "創建房間 CREATE", 
                    color="white", 
                    width=250, 
                    height=50, 
                    style=ft.ButtonStyle(bgcolor=COLOR_ORANGE, shape=ft.RoundedRectangleBorder(radius=10)),
                    on_click=lambda e: submit_action("1")
                ),
                ft.Container(height=10),
                ft.Button(
                    "加入房間 JOIN", 
                    color=COLOR_TEXT, 
                    width=250, 
                    height=50, 
                    style=ft.ButtonStyle(bgcolor=COLOR_GREEN, shape=ft.RoundedRectangleBorder(radius=10)),
                    on_click=lambda e: submit_action("2")
                )
            ])
            
        elif mode == "CREATE_ROOM":
            current_input.hint_text = "例如: 101"
            current_input.label = "輸入房號"
            elements.extend([
                current_input,
                ft.Text("※ 請在下方選單設定密碼字數與回合數後按確認", size=12, color=COLOR_TEXT),
                ft.Button(
                    "下一步 NEXT", 
                    color=COLOR_TEXT, 
                    width=150, 
                    style=ft.ButtonStyle(bgcolor=COLOR_BLUE, shape=ft.RoundedRectangleBorder(radius=10)),
                    on_click=on_btn_click
                )
            ])
            
        elif mode == "GENERIC_INPUT":
            current_input.hint_text = "請輸入數值"
            current_input.label = "Input"
            elements.extend([
                current_input,
                ft.Button(
                    "確認 CHECK", 
                    color=COLOR_TEXT, 
                    width=150, 
                    style=ft.ButtonStyle(bgcolor=COLOR_BLUE, shape=ft.RoundedRectangleBorder(radius=10)),
                    on_click=on_btn_click
                )
            ])

        elif mode == "IN_GAME":
            current_input.hint_text = "輸入數字答案"
            current_input.label = "作答框"
            
            game_card = ft.Container(
                content=ft.Column([
                    system_notification,
                    ft.Divider(color=COLOR_ORANGE),
                    ft.Text("【 猜測實況 】", size=14, weight=ft.FontWeight.BOLD, color=COLOR_TEXT),
                    ft.Container(content=guess_log_view, expand=True, min_height=150)
                ]),
                bgcolor=COLOR_PEACH,
                border_radius=15,
                padding=15,
                expand=True
            )
            elements.extend([
                game_card,
                ft.Row([
                    current_input,
                    ft.IconButton(icon="send", icon_color=COLOR_ORANGE, icon_size=30, on_click=on_btn_click)
                ], alignment=ft.MainAxisAlignment.CENTER)
            ])
            
        elif mode == "GAME_OVER":
            elements.extend([
                ft.Container(content=guess_log_view, expand=True, bgcolor=COLOR_PEACH, padding=15, border_radius=15),
                ft.Button(
                    "回到主畫面", 
                    color="white", 
                    width=250, 
                    height=50, 
                    style=ft.ButtonStyle(bgcolor=COLOR_ORANGE, shape=ft.RoundedRectangleBorder(radius=10)),
                    on_click=lambda e: submit_action("QUIT_LOOP")
                )
            ])

        # 包裝成美美的卡片圓角結構
        card = ft.Container(
            content=ft.Column(elements, alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=15),
            bgcolor="white",
            border_radius=20,
            padding=25,
            margin=10,
            shadow=ft.BoxShadow(blur_radius=10, color="#E0D7D3", offset=ft.Offset(0, 4)),
            expand=True if mode in ["IN_GAME", "GAME_OVER"] else False
        )
        
        view_container.content = card
        page.update()

    # ----------------------------------------------------
    #  背景 TCP 監聽與狀態過濾器
    # ----------------------------------------------------
    def receive_loop():
        global running, current_stage
        render_screen("ENTER_NAME", "ENTER NAME", "請輸入你的名字以建立角色")
        
        while running:
            try:
                message = client.recv(4096).decode()
                if not message:
                    break
                
                clean_msg = message.strip()
                
                if "1. 創建房間" in clean_msg:
                    render_screen("ROOM_CHOICE", "ROOM CHOICE", "請選擇您要發起對局還是加入戰局")
                    continue
                
                if "請輸入房號:" in clean_msg and "已存在" not in clean_msg:
                    render_screen("CREATE_ROOM", "CREATE ROOM", "請輸入房號以建立全新遊戲室")
                    continue
                
                if "請輸入密碼數:" in clean_msg or "請輸入回合數:" in clean_msg:
                    render_screen("GENERIC_INPUT", "SETTING", clean_msg)
                    continue

                if "新回合開始" in clean_msg or "答案已設定" in clean_msg or "作答中" in clean_msg or "猜測結果" in clean_msg or "猜中了答案" in clean_msg or "目前分數" in clean_msg:
                    if current_stage != "IN_GAME":
                        show_pads = "出題者" not in clean_msg
                        render_screen("IN_GAME", "GAME ACTIVE", "對局進行中，請依循輪流機制", show_num_pads=show_pads)
                    
                    lines = clean_msg.split('\n')
                    for line in lines:
                        if not line.strip(): continue
                        if "目前出題者" in line or "輪到玩家" in line or "作答中" in line:
                            system_notification.value = line
                        else:
                            guess_log_view.controls.append(ft.Text(line, color=COLOR_TEXT, size=14))
                    page.update()
                    
                    if "GAME_OVER_RESTART" in clean_msg:
                        render_screen("GAME_OVER", "FINAL RANKING", "本場對局結束，最終結算排名")
                        guess_log_view.controls.append(ft.Text("\n[系統通知] 正在安全返回大廳選單...", color=COLOR_ORANGE))
                        page.update()
                        time.sleep(1.0)
                        client.send("QUIT_LOOP".encode())
                    continue
                
                if guess_log_view.controls is not None:
                    guess_log_view.controls.append(ft.Text(clean_msg, color=COLOR_TEXT))
                    page.update()

            except Exception as ex:
                print(f"Error: {ex}")
                break

    # ----------------------------------------------------
    #  主畫面裝載與啟動
    # ----------------------------------------------------
    page.add(
        ft.Row([
            ft.Column([
                ft.Text("Hello, Player", size=24, weight=ft.FontWeight.BOLD, color=COLOR_TEXT),
                ft.Text("歡迎來到 1A2B 智力對決系統", size=12, color=COLOR_TEXT),
            ]),
            ft.CircleAvatar(bgcolor=COLOR_ORANGE, content=ft.Icon(ft.Icons.PERSON, color="white"))
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, margin=ft.Margin.only(bottom=15)),
        view_container
    )
    
    receive_thread = threading.Thread(target=receive_loop, daemon=True)
    receive_thread.start()

    def on_close(e):
        global running
        running = False
        try: client.close()
        except: pass
            
    page.on_close = on_close

ft.run(main)