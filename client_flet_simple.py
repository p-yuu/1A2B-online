import socket
import threading
import time
import flet as ft

SERVER_IP = '127.0.0.1'  # Demo時記得改成你電腦的區網IP！
SERVER_PORT = 5000

# 建立 TCP Socket 連線
client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect((SERVER_IP, SERVER_PORT))

running = True

def main(page: ft.Page):
    global running
    
    # 1. 視窗基礎設定（滿足黑底白字基本要求）
    page.title = "1A2B 猜數字多人連線系統"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 20
    page.window_width = 450
    page.window_height = 650
    
    # 2. 宣告圖形化UI元件
    # 訊息顯示區（可自動滾動的清單）
    chat_view = ft.ListView(
        expand=True, 
        spacing=10, 
        auto_scroll=True
    )
    
    # 使用者文字輸入框
    input_field = ft.TextField(
        hint_text="請在此輸入回應...",
        expand=True,
        on_submit=lambda e: send_message(e)  # 按下 Enter 也能直接送出
    )
    
    # 發送按鈕
    send_button = ft.IconButton(
        icon="send",  # 直接用小寫字串 "send"
        icon_color="white",
        on_click=lambda e: send_message(e)
    )

    # 3. 定義發送訊號的動作（取代原本的 write 執行緒）
    def send_message(e):
        msg = input_field.value.strip()
        if msg:
            try:
                client.send(msg.encode())
                input_field.value = ""  # 清空輸入框
                page.update()           # 刷新介面
            except:
                chat_view.controls.append(ft.Text("【系統錯誤】無法發送訊息，連線已中斷。", color="red"))
                page.update()

    # 4. 改寫背景接收監聽（維持你的邏輯，但將文字印到畫面上）
    def receive_loop():
        global running
        while running:
            try:
                message = client.recv(1024).decode()
                if not message:
                    break
                
                # 將新訊息轉換為 Flet 元件加進對話區中
                chat_view.controls.append(ft.Text(message, color="white", size=16))
                page.update()  # 關鍵：叫介面重新整理，畫出新文字

                # 完美保留你原先的遊戲重啟解鎖邏輯
                if "GAME_OVER_RESTART" in message:
                    chat_view.controls.append(ft.Text("\n[系統提示] 遊戲結束，正在重新開始...", color="yellow"))
                    page.update()
                    time.sleep(0.5)
                    client.send("QUIT_LOOP".encode())

            except:
                break
                
        chat_view.controls.append(ft.Text("【系統通知】與伺服器斷開連線。", color="red"))
        page.update()

    # 5. 排版佈局
    # 將對話區與底部的輸入面板垂直排列
    page.add(
        ft.Container(
            content=chat_view,
            border=ft.Border.all(1, "white"),
            border_radius=5,
            padding=10,
            expand=True
        ),
        ft.Row(
            controls=[input_field, send_button],
            spacing=10
        )
    )
    
    # 6. 在背景啟動接收 Thread，防範 GUI 卡死
    receive_thread = threading.Thread(target=receive_loop, daemon=True)
    receive_thread.start()

    # 處理當使用者關閉視窗時的釋放動作
    def on_close(e):
        global running
        running = False
        try:
            client.close()
        except:
            pass
            
    page.on_close = on_close

# 啟動 Flet 應用程式
ft.app(main)