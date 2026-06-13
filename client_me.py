import socket
import threading
import time
from queue import Queue
import flet as ft

SERVER_IP = '127.0.0.1'
SERVER_PORT = 5000

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect((SERVER_IP, SERVER_PORT))
running = True

# Flet 與 Socket 溝通用
send_queue = Queue()

# Flet 元件參考
chat_area = None
page_ref = None


def receive():
    global running

    while running:
        try:
            message = client.recv(1024).decode()
            if not message:
                break

            print(message)
            # 顯示到 Flet
            if chat_area and page_ref:
                chat_area.controls.append(ft.Text(message))
                page_ref.update()

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

        except:
            break


def main(page: ft.Page):
    global chat_area
    global page_ref

    page_ref = page

    page.title = "Socket Client"

    chat_area = ft.Column(
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )

    msg_input = ft.TextField(
        hint_text="輸入訊息...",
        expand=True,
    )

    def send_click(e):
        msg = msg_input.value.strip()

        if msg:
            send_queue.put(msg)

            # 本地顯示
            chat_area.controls.append(
                ft.Text(f"我: {msg}")
            )

            msg_input.value = ""

            page.update()

    page.add(
        ft.Column(
            [
                ft.Text("聊天室"),
                chat_area,
                ft.Row(
                    [
                        msg_input,
                        ft.Button(
                            "送出",
                            on_click=send_click,
                        ),
                    ]
                ),
            ],
            expand=True,
        )
    )


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