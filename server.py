import socket
import threading

SERVER_IP = '0.0.0.0'
SERVER_PORT = 5000

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind((SERVER_IP, SERVER_PORT))
server.listen()
server.settimeout(1)
running = True

players = {}
rooms = {}
lock = threading.Lock() 

CHANCE = 10

def send_to_room(room_id, message):
    room = rooms[room_id]
    for client in room["players"]:
        try:
            client.send(message.encode())
        except:
            pass
        

def show_room_players(room_id):
    room = rooms[room_id]
    names = []
    for client in room["players"]:
        names.append(players[client]["name"])
    msg = "\n=== 房間玩家 ===\n"
    for name in names:
        msg += f"{name}\n"
    send_to_room(room_id, msg)


def show_current_scores(room_id):
    score_msg = "=== 目前分數 ===\n"
    room = rooms[room_id]
    for p in room["players"]:
        score_msg += f"{players[p]['name']} : {players[p]['score']} 分\n"
    send_to_room(room_id, score_msg)


def check_answer(answer, guess):
    A = 0
    B = 0
    for i in range(len(answer)):
        if guess[i] == answer[i]:
            A += 1
        elif guess[i] in answer:
            B += 1
    return A, B


def get_next_guesser_index(room, current_index):
    num_players = len(room["players"])
    next_index = (current_index + 1) % num_players
    if next_index == room["current_setter_index"]:
        next_index = (next_index + 1) % num_players
    return next_index


def start_new_round(room_id):
    room = rooms[room_id]

    if room["round_now"] >= len(room["players"]) * room["round_limit"]:
        send_to_room(room_id, "\n遊戲結束")

        score_msg = "\n=== 最終排名 ===\n"
        sorted_players = sorted(room["players"], key=lambda p: players[p]["score"], reverse=True)

        for p in sorted_players:
            score_msg += f"{players[p]['name']}: {players[p]['score']} 分\n"

        send_to_room(room_id, score_msg)
        send_to_room(room_id, "GAME_OVER_RESTART") 
        
        room_players = list(room["players"])
        if room_id in rooms:
            del rooms[room_id]

        for p in room_players:
            if p in players:
                players[p]["room"] = None
                players[p]["history"] = []
                players[p]["score"] = 0 
        return
    
    # 清空所有人的個人歷史紀錄
    for p in room["players"]:
        if p in players:
            players[p]["history"] = []

    setter = room["players"][room["current_setter_index"]]
    setter_name = players[setter]["name"]
    answer_len = room["answer_len"]

    # 改變房間狀態為：等待出題
    room["state"] = "WAITING_FOR_ANSWER"

    send_to_room(room_id, f"\n=== 新回合開始 ===\n目前出題者: {setter_name}")
    setter.send(f"請輸入{answer_len}位不重複數字作為答案:".encode())


def handle_client(client):
    try:
        while True:
            client.send("請輸入你的名字: ".encode())
            name = client.recv(1024).decode().strip()

            taken = False
            for p in players.values():
                if p["name"] == name:
                    taken = True
                    break

            if taken:
                client.send("名字已被使用，請重新輸入\n".encode())
            else:
                break

        players[client] = {
            "name": name, 
            "score": 0, 
            "room": None,
            "history": []
        }

        while True:
            client.send("\n1. 創建房間\n2. 加入房間\n請輸入選項: ".encode())
            choice = client.recv(1024).decode().strip()

            if choice == "1":
                client.send("請輸入房號: ".encode())
                room_id = client.recv(1024).decode().strip()
                while room_id in rooms:
                    client.send("房號已存在，請重新輸入: ".encode())
                    room_id = client.recv(1024).decode().strip()

                client.send("請輸入密碼數: ".encode())           
                answer_len = int(client.recv(1024).decode().strip())
                client.send("請輸入回合數: ".encode())
                round_limit = int(client.recv(1024).decode().strip())

                rooms[room_id] = {
                    "host": client,
                    "players": [client],
                    "started": False,
                    "state": "LOBBY", 
                    "round_limit": round_limit,
                    "round_now": 0,
                    "answer_len": answer_len,
                    "answer": "",
                    "current_setter_index": 0,
                    "current_guesser_index": 0
                }
                players[client]["room"] = room_id
                client.send(f"房間 {room_id} 創建成功，你是房主\n".encode())

            elif choice == "2":
                while True:
                    client.send("請輸入房號: ".encode())
                    room_id = client.recv(1024).decode().strip()

                    if room_id in rooms:
                        break
                    elif room_id.lower() == 'q':
                        client.send("退出連線\n".encode())
                        client.close()
                        return
                    else:
                        client.send("房間不存在，請重新輸入，或輸入 q 退出\n".encode())

                rooms[room_id]["players"].append(client)
                players[client]["room"] = room_id
                send_to_room(room_id, f"{name} 加入房間")

            else:
                client.send("輸入錯誤".encode())
                continue

            show_room_players(room_id)

            room = rooms[room_id]
            game_loop = True
            while game_loop:
                try:
                    msg = client.recv(1024).decode().strip()
                except:
                    break
                if not msg:
                    continue

                if msg == "QUIT_LOOP" or players[client]["room"] is None:
                    game_loop = False
                    break

                # 房主開始遊戲
                if (msg == "start" and client == room["host"] and not room["started"]):
                    if len(room["players"]) < 2:
                        client.send("至少需要2位玩家".encode())
                        continue

                    room["started"] = True
                    send_to_room(room_id, "\n遊戲正式開始")
                    start_new_round(room_id)

                # 遊戲進行中
                elif room["started"]:
                    setter = room["players"][room["current_setter_index"]]
                    answer_len = room["answer_len"]

                    # 等待出題階段
                    if room["state"] == "WAITING_FOR_ANSWER":
                        if client != setter:
                            client.send("等待出題者設定答案中，請稍候...\n".encode())
                            continue
                        
                        # 檢查出題格式
                        if (len(msg) != answer_len or not msg.isdigit() or len(set(msg)) != answer_len):
                            client.send("格式錯誤，請重新輸入:".encode())
                            continue
                        
                        room["answer"] = msg
                        room["state"] = "PLAYING"
                        room["current_guesser_index"] = get_next_guesser_index(room, room["current_setter_index"])
                        current_guesser_name = players[room["players"][room["current_guesser_index"]]]["name"]
                        send_to_room(room_id, f"答案已設定，開始猜題！\n【輪到玩家 {current_guesser_name} 作答】")
                        continue

                    # 猜題階段
                    elif room["state"] == "PLAYING":
                        if client == setter:
                            client.send("你是出題者，無法猜題！\n".encode())
                            continue

                        # 防搶答
                        current_guesser = room["players"][room["current_guesser_index"]]
                        if client != current_guesser:
                            current_guesser_name = players[current_guesser]["name"]
                            client.send(f"尚未輪到你！目前正由 {current_guesser_name} 作答中...\n".encode())
                            continue

                        if len(players[client]["history"]) >= CHANCE:
                            client.send("你已經用完 10 次猜題機會了！\n".encode())
                            
                            # 換下一位玩家作答
                            room["current_guesser_index"] = get_next_guesser_index(room, room["current_guesser_index"])
                            next_guesser_name = players[room["players"][room["current_guesser_index"]]]["name"]
                            send_to_room(room_id, f"【玩家 {players[client]['name']} 次數已滿。下一位作答玩家: {next_guesser_name}】")
                            continue

                        guess = msg
                        if (len(guess) != answer_len or not guess.isdigit() or len(set(guess)) != answer_len):
                            client.send(f"請輸入{answer_len}位不重複數字\n".encode())
                            continue

                        A, B = check_answer(room["answer"], guess)

                        # 發送猜測紀錄
                        players[client]["history"].append(f"{guess} -> {A}A{B}B")
                        remain_chance = CHANCE - len(players[client]["history"])
                        history_msg = (
                            f"\n剩餘猜測次數: {remain_chance} 次\n"
                            f"--- 你的個人猜測紀錄 ---\n"
                            f"{'\n'.join(players[client]['history'])}\n"
                        )
                        client.send(history_msg.encode())
                        for p in room["players"]:
                            if p == client:
                                continue                            
                            try:
                                if p == setter:
                                    p.send(f"\n玩家 {players[client]['name']} 猜測 {guess} -> {A}A{B}B\n".encode())
                                else:
                                    p.send(f"\n玩家 {players[client]['name']} 猜測結果 -> {A}A{B}B\n".encode())
                            except:
                                pass

                        # 有人猜中，立刻終止這一回合
                        if A == answer_len:
                            player_name = players[client]["name"]
                            players[client]["score"] += 1
                            
                            send_to_room(room_id, f"\n{player_name} 猜中了答案！本回合結束\n")
                            show_current_scores(room_id)

                            # 更新回合資訊，進入下一輪
                            room["current_setter_index"] = (room["current_setter_index"] + 1) % len(room["players"])
                            room["round_now"] += 1
                            start_new_round(room_id)
                        else:
                            all_finished = True
                            for p in room["players"]:
                                if p != setter: # 只檢查猜題者
                                    if len(players[p]["history"]) < CHANCE:
                                        all_finished = False
                                        break
                                        
                            if all_finished:
                                send_to_room(room_id, f"\n本回合無人猜中。正確答案是: {room['answer']}\n")
                                show_current_scores(room_id)
                                
                                # 更新回合資訊，強制進入下一輪
                                room["current_setter_index"] = (room["current_setter_index"] + 1) % len(room["players"])
                                room["round_now"] += 1
                                start_new_round(room_id)
                            else:
                                # 還有其他人沒猜滿，換下一位
                                room["current_guesser_index"] = get_next_guesser_index(room, room["current_guesser_index"])
                                next_guesser_name = players[room["players"][room["current_guesser_index"]]]["name"]
                                send_to_room(room_id, f"【本輪作答玩家: {next_guesser_name}】")

    except:
        remove_client(client)

def remove_client(client):
    if client in players:
        room_id = players[client]["room"]
        name = players[client]["name"]

        if room_id and room_id in rooms:
            room = rooms[room_id]
            if client in room["players"]:
                room["players"].remove(client)

            send_to_room(room_id, f"{name} 離開房間")
            show_room_players(room_id)
        del players[client]


try:
    print("Server 啟動成功")
    while running:
        try:
            client, addr = server.accept()
            thread = threading.Thread(target=handle_client, args=(client,), daemon=True)
            thread.start()
        except socket.timeout:
            continue
except KeyboardInterrupt:
    print("\n關閉 server")
finally:
    running = False
    server.close()
