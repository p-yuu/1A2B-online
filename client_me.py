import socket
import threading
import time
from queue import Queue
import flet as ft
import asyncio
import json

SERVER_IP = '10.118.232.146'
SERVER_PORT = 5000

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect((SERVER_IP, SERVER_PORT))
running = True
send_queue = Queue()

# Flet 元件參考
COLOR_BG = "#F9F2EF"        # 柔和的米白底色
COLOR_ORANGE = "#F98C53"    # 活力橘 (主要按鈕、房主)
COLOR_GREEN = "#D2E0AA"     # 草綠色 (加入房間、答題成功)
COLOR_GREEN_TEXT = "#89A43D"     # 草綠色 (加入房間、答題成功)
COLOR_BLUE = "#ABD7FB"      # 水藍色 (開始、加入按鈕)
COLOR_BLUE_TEXT = "#4598DB"      # 水藍色 (開始、加入按鈕)
COLOR_PEACH = "#FCCEB4"     # 淺桃色 (卡片背景)
COLOR_TEXT = "#2C2C2C"      # 深灰色高質感文字
COLOR_GRAY = "#B8B8B8"      # 標記按鈕被點擊後的灰色

chat_area = None
page_ref = None

ui_queue = Queue()
room_members = []
members_column = ft.Column() # 動態更新 UI member list
answer_len = None
curr_answer = None

room_no_exist_text = ft.Text("",size=16,color=ft.Colors.RED)
set_wrong_text = ft.Text("",size=16,color=ft.Colors.RED)

system_list = []
system_column = ft.Column()
remain_chance = None
remain_text = ft.Text("Remain chance: 10",size=20,weight=ft.FontWeight.BOLD,color=COLOR_GREEN_TEXT)
history_list = []
history_column = ft.Column()
setter_history_list = []
setter_history_column = ft.Column()

current_rank = []
current_colume = ft.Column()
final_rank_list = []
final_colume = ft.Column()


def receive():
    global running

    buffer = ""
    while running:
        try:
            data = client.recv(1024).decode()
            if not data:
                break
            buffer += data

            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line:
                    continue

                try:
                    message = json.loads(line)
                except Exception as e:
                    print("JSON parse error:", line)
                    continue

                print("receiver get:", message)
                print("\n-----------")

                msg_type = message.get("type")

                # GAME OVER
                if msg_type == "GAME_OVER_RESTART":
                    print("遊戲結束，正在重新開始...")
                    time.sleep(0.5)
                    client.send("QUIT_LOOP".encode())

                # 顯示到 UI
                elif page_ref is not None:
                    change_page(message)

        except Exception as e:
            print("receive error:", e)
            break

def write():
    global running
    while running:
        try:
            msg = send_queue.get()
            if not running:
                break
            client.send(msg.encode())
            print(f"client send: {msg}")##

        except Exception as e:
            print("WRITE ERROR:", e)

# =============== change page ===============
def change_page(msg):
    global room_members, remain_chance, history_list, setter_history_list, current_rank, final_rank_list, curr_answer
    global room_no_exist_text
    msg_type = msg.get("type")
    data = msg.get("data")

    if msg_type =="CHOOSE_MODE":
        ui_queue.put(("route", "/mode_choose"))

    elif msg_type == "ROOM_ID":
        ui_queue.put(("route", "/create_room"))

    elif msg_type == "ROOM_JOIN_ID":    
        ui_queue.put(("route", "/join_room"))

    elif msg_type == "ROOM_NOT_EXIST":
        def update_ui():
            room_no_exist_text.value = "該房間不存在"
            page_ref.update()
        ui_queue.put(("refresh", update_ui))
    
    elif msg_type == "ROOM_CREATE_SUCCESS":
        ui_queue.put(("route", "/room_waiting_host"))

    elif msg_type == "JOIN_SUCCESS":
        ui_queue.put(("route", "/room_waiting_player"))

    elif msg_type == "ROOM_MEMBER":
        print("update member list")##
        room_members[:] = data
        def update_ui():
            members_column.controls = [
                ft.Text(name) for name in room_members
            ]
            page_ref.update()
        ui_queue.put(("refresh", update_ui))

    elif msg_type == "SET_ANSWER":
        ui_queue.put(("route", "/set_answer"))

    elif msg_type == "PASSWORD_FORMAT_WRONG":
        def update_ui():
            set_wrong_text.value = "答案格式錯誤"
            page_ref.update()
        ui_queue.put(("refresh", update_ui))

    elif msg_type == "SET_SUCCESS":
        ui_queue.put(("route", "/setter_page"))

    elif msg_type == "GAME_START":
        ui_queue.put(("route", "/game_page"))

    elif msg_type == "GAME_DATA":
        remain_chance = msg.get("remain")
        history_list[:] = msg.get("history")
        def update_ui():
            remain_text.value = f"Remain chances: {remain_chance}"
            history_column.controls = [
                ft.Text(history, size=16) for history in history_list
            ]
            page_ref.update()
        ui_queue.put(("refresh", update_ui))
    
    elif msg_type == "SYSTEM":
        system_list.append(data)
        def update_ui():
            system_column.controls = [
                ft.Text(system_msg, size=16) for system_msg in system_list
            ]
            page_ref.update()
        ui_queue.put(("refresh", update_ui))

    elif msg_type == "PLAYER_HISTORY":
        setter_history_list.append(data)
        def update_ui():
            setter_history_column.controls = [
                ft.Text(history_msg, size=16) for history_msg in setter_history_list
            ]
            page_ref.update()
        ui_queue.put(("refresh", update_ui))

    elif msg_type == "SOMEONE_GUESS":
        ui_queue.put(("route", "/curr_rank"))

    elif msg_type == "CURR_SCORE":
        current_rank[:] = data
        def update_ui():
            current_colume.controls = [
                ft.Text(rank_msg, size=16) for rank_msg in current_rank
            ]
            page_ref.update()
        ui_queue.put(("refresh", update_ui))
        reset()

    elif msg_type == "GAME_OVER":
        ui_queue.put(("route", "/final_rank"))

    elif msg_type == "FINAL_RANK":
        final_rank_list[:] = data
        def update_ui():
            final_colume.controls = [
                ft.Text(rank_msg, size=16) for rank_msg in final_rank_list
            ]
            page_ref.update()
        ui_queue.put(("refresh", update_ui))

    elif msg_type == "NO_ONE_GUESS":
        curr_answer = data
        ui_queue.put(("route", "/no_one_guess"))

def reset():
    global system_list, system_column, remain_chance, remain_text, history_list, history_column, setter_history_list
    global setter_history_column, set_wrong_text
    system_list.clear()
    system_column.controls.clear()
    remain_chance = None
    remain_text.value = "Remain chance: 10"
    history_list.clear()
    history_column.controls.clear()
    setter_history_list.clear()
    setter_history_column.controls.clear()
    set_wrong_text.value = ""

def process_ui_queue(page):
    try:
        while True:
            event = ui_queue.get_nowait()
            if event[0] == "route":
                page.go(event[1])
            elif event[0] == "refresh":
                event[1]()
    except:
        pass

async def ui_loop():
    while True:
        process_ui_queue(page_ref)
        page_ref.update()
        await asyncio.sleep(0.1)

# =============== page function ===============
def register(page):
    global SERVER_IP
    ip_input = ft.TextField(label="請輸入伺服器 IP",border_radius=15,width=280,)
    name_input = ft.TextField(label="請輸入你的名字",border_radius=15,width=280,)
    # tile = ft.ExpansionTile(
    #     title=ft.Text("連線設定", color=COLOR_GRAY),
    #     controls=[ip_input,],
    # )

    def start_click(e):
        global SERVER_IP
        player_name = name_input.value.strip()
        # if ip_input.value.strip():
        #     SERVER_IP = ip_input.value.strip()
        if player_name == "":
            return
        send_queue.put(player_name)
        print(f"送出: {player_name}")
        print(f"設定: {SERVER_IP}")

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
                                    tile,
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
    global answer_len
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
        global answer_len
        answer_len = password_len_input.value
        send_msg = room_id_input.value.strip() + '\n' + password_len_input.value + '\n' + round_num_input.value
        send_queue.put(send_msg)
        print("送出: 房間創建完成")

    return ft.View(
                route="/host_setting",
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
                route="/join_room",
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
                                    ft.Container(height=20, content=room_no_exist_text,),
                                    ft.Button("加入",bgcolor=COLOR_BLUE,color=COLOR_TEXT,width=280,height=50,on_click=join_room_click,)
                                ],
                            )
                        ),
                        elevation=10,
                    ),
                ],
            )

def room_waiting_host(page):
    def start(e):
        send_queue.put("start")
        print("送出: 開始遊戲")
    
    return ft.View(
                route="/room_waiting_host",
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
                                    ft.Text("WAITING...",size=30,weight=ft.FontWeight.BOLD,color=COLOR_ORANGE),
                                    ft.Text("等待房主開始遊戲",size=16,color=COLOR_TEXT),
                                    ft.Divider(color=COLOR_PEACH, thickness=2),
                                    ft.Text("房間成員",size=16,color=COLOR_TEXT,weight=ft.FontWeight.BOLD,),
                                    ft.Container(height=120,content=members_column,),
                                    ft.Container(height=80),
                                    ft.Button("開始遊戲",bgcolor=COLOR_GREEN,color=COLOR_TEXT,width=280,height=50,on_click=start,)
                                ],
                            )
                        ),
                        elevation=10,
                    ),
                ],
            )

def room_waiting_player(page): 
    return ft.View(
                route="/room_waiting_player",
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
                                    ft.Text("WAITING...",size=30,weight=ft.FontWeight.BOLD,color=COLOR_ORANGE),
                                    ft.Text("等待房主開始遊戲",size=16,color=COLOR_TEXT),
                                    ft.Divider(color=COLOR_PEACH, thickness=2),
                                    ft.Text("房間成員",size=16,color=COLOR_TEXT,weight=ft.FontWeight.BOLD,),
                                    ft.Container(height=120,content=members_column,),
                                    ft.Container(height=80),
                                ],
                            )
                        ),
                        elevation=10,
                    ),
                ],
            )

def set_answer(page):
    global curr_answer
    ans_input = ft.TextField(label=f"請輸入密碼",border_radius=15,width=280,)

    def start_click(e):
        global curr_answer
        curr_answer = ans_input.value.strip()
        send_queue.put(curr_answer)
        print(f"送出: {curr_answer}")

    return ft.View(
                route="/set_answer",
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
                                    ft.Text("SET ANSWER",size=30,weight=ft.FontWeight.BOLD,color=COLOR_ORANGE),
                                    ft.Text(f"請輸入{answer_len}位不重複數字作為答案",size=16,color=COLOR_TEXT),
                                    ft.Container(height=80),
                                    ans_input,
                                    ft.Container(height=20, content=set_wrong_text,),
                                    ft.Button("設定",bgcolor=COLOR_PEACH,color=COLOR_TEXT,width=280,height=50,on_click=start_click,)
                                ],
                            )
                        ),
                        elevation=10,
                    ),
                ],
            )

def game_page(page):
    system_note = ft.Column(
            height=50,
            width=350,
            scroll=ft.ScrollMode.AUTO,
            controls=system_column,
        )
    history = ft.Column(
            height=200,
            width=350,
            scroll=ft.ScrollMode.AUTO,
            controls=history_column,
        )
    
    def toggle_button(e):
        btn = e.control
        if btn.bgcolor == COLOR_PEACH:
            btn.bgcolor = COLOR_GRAY
        else:
            btn.bgcolor = COLOR_PEACH
        page.update()
    buttons = []
    for i in range(10):
        btn = ft.Button(str(i),width=55,height=30,bgcolor=COLOR_PEACH,color=COLOR_TEXT,on_click=toggle_button,)
        buttons.append(btn)

    guess=ft.TextField(label="請輸入猜測", expand=True)
    def click_send(e):
        send_queue.put(guess.value.strip())
        guess.value = ""
        print(f"送出: guess")

    return ft.View(
                route="/game_page",
                vertical_alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text("ROUND",weight=ft.FontWeight.BOLD,size=30,color=COLOR_ORANGE),
                    ft.Container(height=5),
                    ft.Card(
                        content=ft.Container(
                            width=350,
                            height=100,
                            padding=ft.Padding(left=20,top=5,right=20,bottom=10),
                            border_radius=20,
                            content=ft.Column(
                                controls=[
                                    ft.Text(
                                        "system notification",weight=ft.FontWeight.BOLD,size=20,color=COLOR_BLUE_TEXT),
                                    system_note,
                                ],
                            )
                        ),
                        elevation=5,
                    ),
                    ft.Card(
                        content=ft.Container(
                            width=350,
                            height=500,
                            padding=20,
                            border_radius=20,
                            content=ft.Column(
                                controls=[
                                    remain_text,
                                    ft.Divider(color=COLOR_GREEN, thickness=2),
                                    ft.Text("歷史猜測紀錄",size=16,color=COLOR_TEXT,weight=ft.FontWeight.BOLD,),
                                    ft.Container(height=200, content=ft.Column(controls=[history,],)),
                                    # ft.Container(height=5),
                                    ft.Row(controls=buttons[:5],alignment=ft.MainAxisAlignment.SPACE_EVENLY,),
                                    ft.Row(controls=buttons[5:],alignment=ft.MainAxisAlignment.SPACE_EVENLY,),
                                    ft.Container(height=5),
                                    ft.Row(
                                        controls=[
                                            guess,
                                            ft.IconButton(ft.Icons.SEND,width=50,height=40,icon_color=COLOR_GREEN_TEXT, on_click=click_send,)
                                        ]
                                    )
                                ],
                            )
                        ),
                        elevation=10,
                    ),
                ],
            )

def setter_page(page):
    system_note = ft.Column(
            height=50,
            width=350,
            scroll=ft.ScrollMode.AUTO,
            controls=system_column,
        )
    setter_history = ft.Column(
            height=200,
            width=350,
            scroll=ft.ScrollMode.AUTO,
            controls=setter_history_column,
        )
    
    return ft.View(
                route="/setter_page",
                vertical_alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text("ROUND",weight=ft.FontWeight.BOLD,size=30,color=COLOR_ORANGE),
                    ft.Container(height=5),
                    ft.Card(
                        content=ft.Container(
                            width=350,
                            height=100,
                            padding=ft.Padding(left=20,top=5,right=20,bottom=10),
                            border_radius=20,
                            content=ft.Column(
                                controls=[
                                    ft.Text(
                                        "system notification",weight=ft.FontWeight.BOLD,size=20,color=COLOR_BLUE_TEXT),
                                    system_note,
                                ],
                            )
                        ),
                        elevation=5,
                    ),
                    ft.Card(
                        content=ft.Container(
                            width=350,
                            height=500,
                            padding=20,
                            border_radius=20,
                            content=ft.Column(
                                controls=[
                                    ft.Text("玩家猜測紀錄",size=16,color=COLOR_GREEN_TEXT,weight=ft.FontWeight.BOLD,),
                                    ft.Divider(color=COLOR_GREEN, thickness=2),
                                    ft.Container(height=200, content=ft.Column(controls=[setter_history,],)),
                                ],
                            )
                        ),
                        elevation=10,
                    ),
                ],
            )

def curr_rank(page):
    def next_round(e):
        send_queue.put("check")
        print("送出: 確認進入下一輪")

    return ft.View(
                route="/curr_rank",
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
                                    ft.Text("CURRENT RANK",size=30,weight=ft.FontWeight.BOLD,color=COLOR_ORANGE),
                                    ft.Text("當前分數結算",size=16,color=COLOR_TEXT),
                                    ft.Divider(color=COLOR_PEACH, thickness=2),
                                    ft.Container(height=120,content=current_colume,),
                                    ft.Container(height=80),
                                    ft.Button("NEXT",bgcolor=COLOR_GREEN,color=COLOR_TEXT,width=280,height=50,on_click=next_round,)
                                ],
                            )
                        ),
                        elevation=10,
                    ),
                ],
            )

def final_rank(page):
    def next_round(e):
        send_queue.put("check")
        print("送出: 確認結束")

    return ft.View(
                route="/final_rank",
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
                                    ft.Text("FINAL RANK",size=30,weight=ft.FontWeight.BOLD,color=COLOR_ORANGE),
                                    ft.Text("最終排名",size=16,color=COLOR_TEXT),
                                    ft.Divider(color=COLOR_PEACH, thickness=2),
                                    ft.Container(height=120,content=final_colume,),
                                    ft.Container(height=80),
                                    ft.Button("返回主頁",bgcolor=COLOR_PEACH,color=COLOR_TEXT,width=280,height=50,on_click=next_round,)
                                ],
                            )
                        ),
                        elevation=10,
                    ),
                ],
            )

def no_one_guess(page):
    def next_round(e):
        send_queue.put("check")
        print("送出: 進入 curr rank")

    return ft.View(
                route="/no_one_guess",
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
                                    ft.Text("NO ONE GUESSED",size=30,weight=ft.FontWeight.BOLD,color=COLOR_ORANGE),
                                    ft.Text("沒有人猜中答案",size=16,color=COLOR_TEXT),
                                    ft.Divider(color=COLOR_PEACH, thickness=2),
                                    ft.Text("正確答案",size=16,color=COLOR_TEXT),
                                    ft.Text(curr_answer,weight=ft.FontWeight.BOLD,size=25,color=COLOR_TEXT),
                                    ft.Container(height=120),
                                    ft.Button("NEXT",bgcolor=COLOR_BLUE,color=COLOR_TEXT,width=280,height=50,on_click=next_round)
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

        elif page.route == "/room_waiting_host":
            page.views.append(room_waiting_host(page))

        elif page.route == "/room_waiting_player":
            page.views.append(room_waiting_player(page))

        elif page.route == "/set_answer":
            page.views.append(set_answer(page))

        elif page.route == "/set_answer":
            page.views.append(set_answer(page))

        elif page.route == "/game_page":
            page.views.append(game_page(page))

        elif page.route == "/setter_page":
            page.views.append(setter_page(page))

        elif page.route == "/curr_rank":
            page.views.append(curr_rank(page))

        elif page.route == "/final_rank":
            page.views.append(final_rank(page))

        elif page.route == "/no_one_guess":
            page.views.append(no_one_guess(page))

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