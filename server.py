import socket
import threading
import json

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

def recv_msg(client, buffer):
    data = client.recv(1024).decode()
    if not data:
        return None, None, buffer
    buffer += data

    if "\n" not in buffer:
        return None, None, buffer

    line, buffer = buffer.split("\n", 1)
    line = line.strip()

    if not line:
        return None, None, buffer

    try:
        msg = json.loads(line)
        return msg.get("type"), msg.get("data"), buffer

    except json.JSONDecodeError:
        return None, line, buffer

def send_to_room(room_id, message):
    if room_id not in rooms:
        return
    with lock:
        current_players = list(rooms[room_id]["players"])
    for client in current_players:
        try:
            client.sendall((json.dumps(message) + "\n").encode())
        except:
            pass
        

def show_room_players(room_id):
    with lock:
        if room_id not in rooms:
            return
        room = rooms[room_id]
        names = [players[client]["name"] for client in room["players"] if client in players]
                
    msg = {"type": "ROOM_MEMBER", "data": names}
    send_to_room(room_id, msg)


def show_current_scores(room_id, client, buffer):
    curr_score = []
    with lock:
        if room_id not in rooms:
            return buffer
        room = rooms[room_id]
        for p in room["players"]:
            if p in players:
                curr_score.append(f"{players[p]['name']} : {players[p]['score']} 分")
    msg = {"type": "CURR_SCORE", "data": curr_score}
    send_to_room(room_id, msg)
    msg_type, check, buffer = recv_msg(client, buffer)
    
    if not check:
        return buffer
    return buffer


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


def start_new_round(room_id, client, buffer):
    with lock:
        if room_id not in rooms:
            return
        room = rooms[room_id]

    if room["round_now"] >= len(room["players"]) * room["round_limit"]:
        send_to_room(room_id, {"type": "GAME_OVER"})

        final_rank = []
        with lock:
            sorted_players = sorted(room["players"], key=lambda p: players[p]["score"] if p in players else 0, reverse=True)
            cnt = 1
            for p in sorted_players:
                if p in players:
                    final_rank.append(f"第 {cnt} 名: {players[p]['name']} -> {players[p]['score']} 分")
                    cnt += 1

        send_to_room(room_id, {"type": "FINAL_RANK", "data": final_rank})
        return buffer
    
    # 清空所有人的個人歷史紀錄
    with lock:
        for p in room["players"]:
            if p in players:
                players[p]["history"] = []

        setter = room["players"][room["current_setter_index"]]
        setter_name = players[setter]["name"] if setter in players else "Unknown"
        answer_len = room["answer_len"]
        room["state"] = "WAITING_FOR_ANSWER"

    send_to_room(room_id, {"type": "GAME_START"})
    send_to_room(room_id, {"type": "SYSTEM", "data": f"新回合開始，目前出題者為 {setter_name}"})
    try:
        setter.sendall((json.dumps({"type":"SET_ANSWER"}) + "\n").encode())
    except:
        pass
    return buffer

def handle_client(client):
    try:
        buffer = ""
        while True:
            client.sendall((json.dumps({"type":"NAME"}) + "\n").encode())
            msg_type, name, buffer = recv_msg(client, buffer)
            if not name:
                return

            with lock:
                taken = any(p["name"] == name for p in players.values())

            if taken:
                client.sendall((json.dumps({"type":"NAME_USED"}) + "\n").encode())
            else:
                break

        with lock:
            players[client] = {
                "name": name, 
                "score": 0, 
                "room": None,
                "history": []
            }

        while True:
            client.sendall((json.dumps({"type":"CHOOSE_MODE"}) + "\n").encode())
            msg_type, choice, buffer = recv_msg(client, buffer)
            if not choice: return

            if choice == "1":
                client.sendall((json.dumps({"type":"ROOM_ID"}) + "\n").encode())
                msg_type, room_id, buffer = recv_msg(client, buffer)
                if not room_id: return

                setting_msg = room_id.split("\n")
                room_id = setting_msg[0]
                answer_len = int(setting_msg[1])
                round_limit = int(setting_msg[2])

                with lock:
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
                        "current_guesser_index": 0,
                        "confirm_restart": set()
                    }
                    players[client]["room"] = room_id
                client.sendall((json.dumps({"type":"ROOM_CREATE_SUCCESS"}) + "\n").encode())

            elif choice == "2":
                while True:
                    client.sendall((json.dumps({"type":"ROOM_JOIN_ID"}) + "\n").encode())
                    msg_type, room_id, buffer = recv_msg(client, buffer)
                    if not room_id: return

                    with lock:
                        room_exists = room_id in rooms
                    if room_exists:
                        break
                    else:
                        client.sendall((json.dumps({"type":"ROOM_NOT_EXIST"}) + "\n").encode())

                with lock:
                    rooms[room_id]["players"].append(client)
                    players[client]["room"] = room_id

                client.sendall((json.dumps({"type":"JOIN_SUCCESS"}) + "\n").encode())

            else:
                client.sendall((json.dumps({"type":"輸入錯誤"}) + "\n").encode())
                continue

            show_room_players(room_id)

            game_loop = True
            while game_loop:
                try:
                    msg_type, msg, buffer = recv_msg(client, buffer)
                except:
                    break
                if not msg:
                    continue

                with lock:
                    current_room_id = players[client]["room"]
                    if client not in players or current_room_id is None or current_room_id not in rooms:
                        game_loop = False
                        break
                    room = rooms[current_room_id]

                if msg_type == "QUIT_LOOP":
                    game_loop = False
                    break

                elif msg_type == "image":
                    send_to_room(room_id, {"type": "IMAGE", "data": msg})
                    

                elif msg_type == "CONFIRM_GAME_OVER":
                    should_restart = False
                    room_players = []

                    with lock:
                        room = rooms.get(room_id)
                        if not room:
                            return

                        room.setdefault("confirm_restart", set())
                        room["confirm_restart"].add(client)

                        if room["confirm_restart"] == set(room["players"]):
                            should_restart = True

                            room_players = list(room["players"])
                            for p in room_players:
                                if p in players:
                                    players[p]["room"] = None
                                    players[p]["history"] = []
                                    players[p]["score"] = 0

                    if should_restart:
                        send_to_room(room_id, {"type": "GAME_OVER_RESTART"})

                        with lock:
                            if room_id in rooms:
                                del rooms[room_id]

                # 房主開始遊戲
                if (msg == "start" and client == room["host"] and not room["started"]):
                    if len(room["players"]) < 2:                        
                        client.sendall((json.dumps({"type":"NOT_ENOUGH_PLAYER"}) + "\n").encode())
                        continue

                    with lock:
                        room["started"] = True
                    buffer = start_new_round(room_id,client, buffer)

                # 遊戲進行中
                elif room["started"]:
                    with lock:
                        setter = room["players"][room["current_setter_index"]]
                        answer_len = room["answer_len"]
                        room_state = room["state"]

                    # 等待出題階段
                    if room_state == "WAITING_FOR_ANSWER":
                        if client != setter:                            
                            client.sendall((json.dumps({"type":"SYSTEM", "data": "等待出題者設定答案中，請稍候..."}) + "\n").encode())
                            continue

                        # 檢查出題格式
                        if (len(msg) != answer_len or not msg.isdigit() or len(set(msg)) != answer_len):                            
                            client.sendall((json.dumps({"type":"PASSWORD_FORMAT_WRONG"}) + "\n").encode())
                            continue

                        with lock:
                            room["answer"] = msg
                            room["state"] = "PLAYING"
                            room["current_guesser_index"] = get_next_guesser_index(room, room["current_setter_index"])
                            current_guesser_name = players[room["players"][room["current_guesser_index"]]]["name"]

                        client.sendall((json.dumps({"type":"SET_SUCCESS"}) + "\n").encode())
                        send_to_room(current_room_id, {"type":"SYSTEM", "data": f"答案已設定，輪到玩家 {current_guesser_name} 作答"})
                        continue

                    # 猜題階段
                    elif room_state == "PLAYING":
                        if client == setter:                            
                            client.sendall((json.dumps({"type":"SYSTEM", "data": "你是出題者，無法猜題"}) + "\n").encode())
                            continue

                        # 防搶答
                        with lock:
                            current_guesser = room["players"][room["current_guesser_index"]]
                        if client != current_guesser:
                            with lock:
                                current_guesser_name = players[current_guesser]["name"]                                
                            client.sendall((json.dumps({"type":"SYSTEM", "data": f"尚未輪到你，目前正由 {current_guesser_name} 作答中"}) + "\n").encode())
                            continue

                        with lock:
                            history_count = len(players[client]["history"])
                        if history_count >= CHANCE:                            
                            client.sendall((json.dumps({"type":"SYSTEM", "data": "你已經用完 10 次猜題機會了！"}) + "\n").encode())
                            
                            # 換下一位玩家作答
                            with lock:
                                room["current_guesser_index"] = get_next_guesser_index(room, room["current_guesser_index"])
                                next_guesser_name = players[room["players"][room["current_guesser_index"]]]["name"]
                            send_to_room(room_id, {"type":"SYSTEM", "data": f"玩家 {players[client]['name']} 次數已滿。下一位作答玩家為 {next_guesser_name}"})
                            continue

                        guess = msg
                        if (len(guess) != answer_len or not guess.isdigit() or len(set(guess)) != answer_len):       
                            client.sendall((json.dumps({"type":"SYSTEM", "data": f"請輸入{answer_len}位不重複數字"}) + "\n").encode())
                            continue

                        # 發送猜測紀錄
                        with lock:
                            target_answer = room["answer"]
                        A, B = check_answer(target_answer, guess)

                        with lock:
                            players[client]["history"].append(f"{guess} -> {A}A{B}B")
                            remain_chance = CHANCE - len(players[client]["history"])
                            history_list = list(players[client]["history"])
                            client_name = players[client]["name"]
                            
                        client.sendall((json.dumps({"type":"GAME_DATA", "remain": remain_chance, "history": history_list}) + "\n").encode())
                                                
                        with lock:
                            room_players_snapshot = list(room["players"])
                        for p in room_players_snapshot:
                            if p == client: continue                                     
                            try:
                                if p == setter:
                                    p.sendall((json.dumps({"type":"PLAYER_HISTORY", "data": f"玩家 {client_name} 猜測 {guess} -> {A}A{B}B"}) + "\n").encode())
                                else:                                    
                                    p.sendall((json.dumps({"type":"SYSTEM", "data": f"玩家 {client_name} 猜測結果 -> {A}A{B}B"}) + "\n").encode())
                            except:
                                pass

                        # 有人猜中，立刻終止這一回合
                        if A == answer_len:
                            with lock:
                                players[client]["score"] += 1
                            send_to_room(current_room_id, {"type": "SOMEONE_GUESS"})
                            buffer = show_current_scores(current_room_id, client, buffer)

                            # 更新回合資訊，進入下一輪
                            with lock:
                                room["current_setter_index"] = (room["current_setter_index"] + 1) % len(room["players"])
                                room["round_now"] += 1
                            buffer = start_new_round(current_room_id,client, buffer)
                        else:
                            all_finished = True
                            with lock:
                                for p in room["players"]:
                                    if p != setter and p in players:
                                        if len(players[p]["history"]) < CHANCE:
                                            all_finished = False
                                            break
                                        
                            if all_finished:
                                send_to_room(room_id, {"type": "NO_ONE_GUESS", "data": room['answer']})
                                msg_type, check, buffer = recv_msg(client, buffer)
                                if not check:
                                    return
                                send_to_room(room_id, {"type": "SOMEONE_GUESS"})
                                buffer = show_current_scores(room_id,client, buffer)
                                
                                # 更新回合資訊，強制進入下一輪
                                with lock:
                                    room["current_setter_index"] = (room["current_setter_index"] + 1) % len(room["players"])
                                    room["round_now"] += 1
                                buffer = start_new_round(current_room_id,client, buffer)
                            else:
                                # 還有其他人沒猜滿，換下一位
                                with lock:
                                    room["current_guesser_index"] = get_next_guesser_index(room, room["current_guesser_index"])
                                    next_guesser_name = players[room["players"][room["current_guesser_index"]]]["name"]
                                send_to_room(current_room_id, {"type": "SYSTEM", "data": f"本輪作答玩家為 {next_guesser_name}"})
                with lock:
                    if client not in players or players[client]["room"] is None:
                        game_loop = False
                        break
    except:
        pass
    finally:
        remove_client(client)

def remove_client(client):
    with lock:
        if client not in players:
            return
        room_id = players[client]["room"]
        name = players[client]["name"]
        del players[client]

        if room_id and room_id in rooms:
            room = rooms[room_id]
            if client in room["players"]:
                room["players"].remove(client)

            # 如果遊戲進行中有人退出，直接強制中止房間，避免遺留玩家卡死
            if room["started"]:
                send_to_room(room_id, {"type": "SYSTEM", "data": f"【系統警告】玩家 {name} 在遊戲中斷線，對局強制結束！"})
                send_to_room(room_id, {"type": "GAME_OVER_RESTART"})
                for p in list(room["players"]):
                    if p in players:
                        players[p]["room"] = None
                        players[p]["history"] = []
                        players[p]["score"] = 0
                if room_id in rooms:
                    del rooms[room_id]
                return

            send_to_room(room_id, {"type": "SYSTEM", "data": f"{name} 離開房間"})
            show_room_players(room_id)


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
