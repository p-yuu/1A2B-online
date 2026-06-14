import socket
import threading
import time
import json

SERVER_IP = '127.0.0.1'
SERVER_PORT = 5000

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect((SERVER_IP, SERVER_PORT))

running = True

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

                msg_type = message.get("type")

                # GAME OVER
                if msg_type == "GAME_OVER_RESTART":
                    print("遊戲結束，正在重新開始...")
                    time.sleep(0.5)
                    client.send("QUIT_LOOP".encode())

        except Exception as e:
            print("receive error:", e)
            break


def write():
    global running
    while running:
        try:
            msg = input()
            if not running:
                break
            client.send(msg.encode())
        except:
            break

receive_thread = threading.Thread(target = receive, daemon = True)  # daemon=True 讓執行緒在主程式結束時自動結束
write_thread = threading.Thread(target = write, daemon = True)

try:
    receive_thread.start()
    write_thread.start()

    while running:
        receive_thread.join(timeout=0.1)  # 使用 timeout 讓主程式可以定期檢查 running 狀態

except KeyboardInterrupt:
    print("\n關閉 client")
    running = False
    client.close()