import socket
import threading
import time
from queue import Queue
import flet as ft
import asyncio

SERVER_IP = '127.0.0.1'
SERVER_PORT = 5000

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect((SERVER_IP, SERVER_PORT))
running = True
send_queue = Queue()
ui_queue = Queue()

# Flet 元件參考
chat_area = None
page_ref = None

COLOR_BG = "#F9F2EF"        # 柔和的米白底色
COLOR_ORANGE = "#F98C53"    # 活力橘 (主要按鈕、房主)
COLOR_GREEN = "#D2E0AA"     # 草綠色 (加入房間、答題成功)
COLOR_BLUE = "#ABD7FB"      # 水藍色 (開始、加入按鈕)
COLOR_PEACH = "#FCCEB4"     # 淺桃色 (卡片背景)
COLOR_TEXT = "#2C2C2C"      # 深灰色高質感文字
COLOR_GRAY = "#9E9E9E"      # 標記按鈕被點擊後的灰色


def receive():
    global running

    while running:
        try:
            message = client.recv(1024).decode()
            if not message:
                break

            print(message)
            # 顯示到 Flet
            if page_ref is not None:
                change_page(message)

            if "GAME_OVER_RESTART" in message:
                print("遊戲結束，正在重新開始...")
                time.sleep(0.5)
                client.send("QUIT_LOOP".encode())

        except:
            break

def write():
    global running
    while running:
        try:
            msg = send_queue.get()
            if not running:
                break
            client.send(msg.encode())

        except Exception as e:
            print("WRITE ERROR:", e)

# =============== change page ===============
def change_page(msg):
    msg = msg.strip()
    if msg.startswith("CHOOSE_MODE"):
        ui_queue.put("/mode_choose")
    elif msg.startswith("ROOM_ID"):
        ui_queue.put("/create_room")
    elif msg.startswith("ROOM_JOIN_ID"):    
        ui_queue.put("/join_room")

def process_ui_queue(page):
    try:
        while True:
            route = ui_queue.get_nowait()
            page.go(route)
    except:
        pass

async def ui_loop():
    while True:
        process_ui_queue(page_ref)
        page_ref.update()
        await asyncio.sleep(0.1)

# =============== page function ===============
def register(page):
    name_input = ft.TextField(label="請輸入你的名字",border_radius=15,width=280,)

    def start_click(e):
        player_name = name_input.value.strip()
        if player_name == "":
            return
        send_queue.put(player_name)
        print(f"送出: {player_name}")

    return ft.View(
                route="/",
                vertical_alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Card(
                        content=ft.Container(
                            width=350,
                            height=500,
                            padding=30,
                            border_radius=20,
                            content=ft.Column(
                                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                controls=[
                                    ft.Text("1A2B ONLINE",size=30,weight=ft.FontWeight.BOLD,color=COLOR_ORANGE),
                                    ft.Text("歡迎來到 1A2B online",size=16,color=COLOR_TEXT),
                                    ft.Container(height=80),
                                    name_input,
                                    ft.Container(height=15),
                                    ft.Button("START 開始",bgcolor=COLOR_BLUE,color=COLOR_TEXT,width=280,height=50,on_click=start_click,)
                                ],
                            )
                        ),
                        elevation=10,
                    ),
                ],
            )

def mode_choose(page):
    def create_room(e):
        send_queue.put("1")
        print("送出: 創建房間")

    def join_room(e):
        send_queue.put("2")
        print("送出: 創建房間")
        
    return ft.View(
                route="/mode_choose",
                vertical_alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Card(
                        content=ft.Container(
                            width=350,
                            height=500,
                            padding=30,
                            border_radius=20,
                            content=ft.Column(
                                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                controls=[
                                    ft.Text("MODE CHOICE",size=30,weight=ft.FontWeight.BOLD,color=COLOR_ORANGE),
                                    ft.Text("請選擇模式",size=16,color=COLOR_TEXT),
                                    ft.Container(height=60),
                                    ft.Button("創建房間 CREATE",bgcolor=COLOR_ORANGE,color=COLOR_BG,width=280,height=50,on_click=create_room,),
                                    ft.Container(height=5),
                                    ft.Button("加入房間 JOIN",bgcolor=COLOR_GREEN,color=COLOR_TEXT,width=280,height=50,on_click=join_room,)
                                ],
                            )
                        ),
                        elevation=10,
                    ),
                ],
            )

def host_setting(page):
    room_id_input = ft.TextField(label="請輸房號",border_radius=15,width=280,)
    password_len_input= ft.Dropdown(width=200,
                        options=[
                            ft.dropdown.Option("1"),
                            ft.dropdown.Option("2"),
                            ft.dropdown.Option("3"),
                            ft.dropdown.Option("4"),
                            ft.dropdown.Option("5"),
                            ft.dropdown.Option("6"),
                            ft.dropdown.Option("7"),
                            ft.dropdown.Option("8"),
                            ft.dropdown.Option("9"),
                            ft.dropdown.Option("10"),
                        ]
                    )
    round_num_input = ft.Dropdown(width=200,
                        options=[
                            ft.dropdown.Option("1"),
                            ft.dropdown.Option("2"),
                            ft.dropdown.Option("3"),
                            ft.dropdown.Option("4"),
                            ft.dropdown.Option("5"),
                            ft.dropdown.Option("6"),
                            ft.dropdown.Option("7"),
                            ft.dropdown.Option("8"),
                            ft.dropdown.Option("9"),
                            ft.dropdown.Option("10"),
                        ]
                    )

    def finish_setting(e):
        send_queue.put(room_id_input.value.strip())
        send_queue.put(password_len_input.value)
        send_queue.put(round_num_input.value)
        print("送出: 房間創建完成")

    return ft.View(
                route="/create_room",
                vertical_alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Card(
                        content=ft.Container(
                            width=350,
                            height=500,
                            padding=30,
                            border_radius=20,
                            content=ft.Column(
                                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                controls=[
                                        ft.Text("CREATE ROOM",size=30,weight=ft.FontWeight.BOLD,color=COLOR_ORANGE),
                                        ft.Text("請完成您的遊戲設定",size=16,color=COLOR_TEXT),
                                        ft.Container(height=10),
                                        room_id_input,
                                        ft.Container(height=5),
                                        ft.Text("請選擇密碼長度",size=16,color=COLOR_TEXT),
                                        password_len_input,
                                        ft.Container(height=5),
                                        ft.Text("請選擇遊戲回合數",size=16,color=COLOR_TEXT),
                                        round_num_input,
                                        ft.Container(height=10),
                                        ft.Button("創建房間",bgcolor=COLOR_BLUE,color=COLOR_TEXT,width=150,height=50, on_click=finish_setting,),
                                    ],
                            )
                        ),
                        elevation=10,
                    ),
                ],
            )

def join_room(page):
    room_id = ft.TextField(label="請輸入房號",border_radius=15,width=280,)
    def join_room_click(e):
        send_queue.put(room_id.value.strip())
        print("送出: 加入房間")

    return ft.View(
                route="/",
                vertical_alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Card(
                        content=ft.Container(
                            width=350,
                            height=500,
                            padding=30,
                            border_radius=20,
                            content=ft.Column(
                                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                controls=[
                                    ft.Text("JOIN ROOM",size=30,weight=ft.FontWeight.BOLD,color=COLOR_ORANGE),
                                    ft.Text("加入已經創建好的房間吧",size=16,color=COLOR_TEXT),
                                    ft.Container(height=80),
                                    room_id,
                                    ft.Container(height=15),
                                    ft.Button("加入",bgcolor=COLOR_BLUE,color=COLOR_TEXT,width=280,height=50,on_click=join_room_click,)
                                ],
                            )
                        ),
                        elevation=10,
                    ),
                ],
            )

def main(page: ft.Page):
    global chat_area
    global page_ref
    page_ref = page

    # =============== init ===============
    page.title = "1A2B online"
    page.bgcolor = COLOR_BG
    page.window.width = 410
    page.window.height = 820

    page.run_task(ui_loop)
    # =============== page setup ===============
    def route_change(e):
        page.views.clear()
        if page.route == "/":
            page.views.append(register(page))
        elif page.route == "/mode_choose":
            page.views.append(mode_choose(page))
        elif page.route == "/create_room":
            page.views.append(host_setting(page))
        elif page.route == "/join_room":
            page.views.append(join_room(page))
        page.update()

    page.on_route_change = route_change
    page.go("/")
    route_change(None)

receive_thread = threading.Thread(target=receive,daemon=True)
write_thread = threading.Thread(target=write,daemon=True)

receive_thread.start()
write_thread.start()

try:
    ft.run(main)

except KeyboardInterrupt:
    print("\n關閉 client")
    running = False
    client.close()