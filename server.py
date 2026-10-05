#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Roblox RP Внешний Чат-Оверлей - Сервер Реального Времени
=========================================================
Высокопроизводительный сервер Socket.IO на базе aiohttp для сессий ролевой игры (RP) в Roblox.
Обеспечивает:
- Работу приватных комнат (каналов RP-сессий)
- Синхронную доставку сообщений участникам
- Вычисление серверного рандома для команд (/try с шансом 50/50: Удачно или Неудачно)
- Форматирование RP-команд (/me, /do, /try, /b, /s, /c)
- Хранение истории последних сообщений (бэклог для вновь подключившихся)
- Мониторинг активных пользователей и комнат (/health)

Запуск:
    python server.py
    python server.py --host 0.0.0.0 --port 5000
"""

import argparse
import datetime
import html
import logging
import random
from typing import Any, Dict

from aiohttp import web
import socketio

# Настройка логирования на русском языке
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("RobloxRPServer")

# Инициализация асинхронного сервера Socket.IO
sio = socketio.AsyncServer(
    async_mode="aiohttp",
    cors_allowed_origins="*",
    ping_timeout=25,
    ping_interval=10,
)
app = web.Application()
sio.attach(app)

# Хранилище подключенных пользователей и комнат в оперативной памяти
connected_users: Dict[str, Dict[str, Any]] = {}
rooms: Dict[str, Dict[str, Any]] = {}

MAX_HISTORY_PER_ROOM = 100

# Стандартная палитра для автоматического выбора цвета никнейма
DEFAULT_PALETTE = [
    "#5CABFF",  # Небесно-голубой
    "#FF5C5C",  # Алый
    "#5CFF88",  # Изумрудный
    "#FFB85C",  # Янтарно-оранжевый
    "#D97BFF",  # Фиолетовый
    "#5CFFE6",  # Бирюзовый
    "#FFE85C",  # Золотистый
    "#FF7BC2",  # Розовый неон
]


def pick_color_for_name(name: str) -> str:
    """Детерминированный выбор цвета никнейма на основе хэша имени."""
    val = sum(ord(c) for c in name)
    return DEFAULT_PALETTE[val % len(DEFAULT_PALETTE)]


def get_current_timestamp() -> str:
    """Получение текущего времени в формате ЧЧ:ММ:СС."""
    return datetime.datetime.now().strftime("%H:%M:%S")


def sanitize_input(text: str) -> str:
    """Очистка ввода от нежелательных управляющих символов и пробелов."""
    if not isinstance(text, str):
        return ""
    # Очищаем от невидимых управляющих символов кроме переноса строк и пробелов
    clean = "".join(ch for ch in text if ch.isprintable() or ch in ("\n", "\t"))
    return clean.strip()


@sio.event
async def connect(sid: str, environ: dict):
    """Событие подключения нового клиента к сокету."""
    client_ip = environ.get("REMOTE_ADDR", "неизвестно")
    logger.info(f"Клиент подключился: SID={sid} (IP: {client_ip})")
    await sio.emit(
        "server_status",
        {
            "status": "connected",
            "message": "Успешное подключение к серверу чата Roblox RP",
            "timestamp": get_current_timestamp(),
        },
        to=sid,
    )


@sio.event
async def disconnect(sid: str):
    """Событие отключения клиента. Оповещает участников комнаты и очищает ресурсы."""
    logger.info(f"Клиент отключился: SID={sid}")
    if sid in connected_users:
        user_info = connected_users.pop(sid)
        room_name = user_info.get("room")
        username = user_info.get("username", "Игрок")

        if room_name and room_name in rooms:
            room_data = rooms[room_name]
            room_data["members"].pop(sid, None)

            # Системное сообщение об уходе
            leave_msg = {
                "id": f"sys-{int(datetime.datetime.now().timestamp()*1000)}",
                "type": "system",
                "author": "Система",
                "color": "#E5A93C",
                "text": f"<- {username} покинул(а) RP-сессию.",
                "timestamp": get_current_timestamp(),
            }
            room_data["history"].append(leave_msg)
            if len(room_data["history"]) > MAX_HISTORY_PER_ROOM:
                room_data["history"].pop(0)

            # Рассылка сообщения и обновленного списка игроков
            await sio.emit("message", leave_msg, room=room_name)
            await sio.emit(
                "room_roster",
                {
                    "room": room_name,
                    "members": list(room_data["members"].values()),
                },
                room=room_name,
            )

            # Удаление комнаты, если она опустела
            if len(room_data["members"]) == 0:
                logger.info(f"Комната '{room_name}' опустела и была удалена.")
                del rooms[room_name]


@sio.event
async def join_room(sid: str, data: dict):
    """
    Вход игрока в приватную RP-комнату.
    Входные данные: {"username": str, "room": str, "color": str, "role": str}
    """
    if not isinstance(data, dict):
        await sio.emit("error_msg", {"error": "Неверный формат данных."}, to=sid)
        return

    raw_username = data.get("username", "").strip() or f"Игрок_{sid[:4]}"
    username = sanitize_input(raw_username)[:32]
    raw_room = data.get("room", "").strip() or "ROBLOX-RP-1"
    # Очищаем имя комнаты от спецсимволов HTML, оставляя только буквы, цифры, дефис и подчеркивание
    room_name = "".join(c for c in raw_room.upper() if c.isalnum() or c in ("-", "_"))[:24] or "ROBLOX-RP-1"

    color = data.get("color")
    if not color or not color.startswith("#"):
        color = pick_color_for_name(username)

    raw_role = data.get("role", "Гражданский")
    role = sanitize_input(str(raw_role))[:24]

    # Если игрок уже был в другой комнате, покидаем ее
    if sid in connected_users:
        old_room = connected_users[sid].get("room")
        if old_room and old_room != room_name:
            await sio.leave_room(sid, old_room)
            if old_room in rooms and sid in rooms[old_room]["members"]:
                del rooms[old_room]["members"][sid]

    # Добавляем сокет в новую комнату Socket.IO
    await sio.enter_room(sid, room_name)

    user_info = {
        "sid": sid,
        "username": username,
        "room": room_name,
        "color": color,
        "role": role,
        "joined_at": get_current_timestamp(),
    }
    connected_users[sid] = user_info

    if room_name not in rooms:
        rooms[room_name] = {"members": {}, "history": []}

    rooms[room_name]["members"][sid] = user_info

    logger.info(f"Игрок '{username}' [{role}] вошел в комнату '{room_name}'.")

    # Отправляем подтверждение и историю последних сообщений
    await sio.emit(
        "joined_success",
        {
            "room": room_name,
            "user": user_info,
            "history": rooms[room_name]["history"][-50:],
            "members": list(rooms[room_name]["members"].values()),
        },
        to=sid,
    )

    # Системное уведомление остальным участникам комнаты
    join_msg = {
        "id": f"sys-{int(datetime.datetime.now().timestamp()*1000)}",
        "type": "system",
        "author": "Система",
        "color": "#4CE595",
        "text": f"-> {username} ({role}) подключился к каналу [{room_name}].",
        "timestamp": get_current_timestamp(),
    }
    rooms[room_name]["history"].append(join_msg)
    if len(rooms[room_name]["history"]) > MAX_HISTORY_PER_ROOM:
        rooms[room_name]["history"].pop(0)

    await sio.emit("message", join_msg, room=room_name)
    await sio.emit(
        "room_roster",
        {
            "room": room_name,
            "members": list(rooms[room_name]["members"].values()),
        },
        room=room_name,
    )


@sio.event
async def send_message(sid: str, data: dict):
    """
    Обработка входящего сообщения или RP-команды.
    Форматы:
    /me <действие>
    /do <окружение>
    /try <действие> (шанс 50/50, кубик 1-100)
    /roll [макс]
    /ooc <текст> или // <текст>
    /s <крик>
    /w <шёпот>
    /help
    /clear
    """
    if sid not in connected_users:
        await sio.emit(
            "error_msg", {"error": "Вы должны сначала войти в комнату."}, to=sid
        )
        return

    user = connected_users[sid]
    room_name = user["room"]
    username = user["username"]
    user_color = user["color"]
    role = user["role"]

    raw_text = data.get("text", "").strip()
    if not raw_text:
        return

    if len(raw_text) > 400:
        raw_text = raw_text[:400]

    ts = get_current_timestamp()
    msg_id = f"msg-{int(datetime.datetime.now().timestamp()*1000)}-{random.randint(100, 999)}"
    clean_text = sanitize_input(raw_text)

    # 1. Команда /help (Справка)
    if clean_text.lower() in ("/help", "/помощь", "/commands", "/команды", "/?"):
        help_text = (
            "<b>Справка по RP-командам чата Roblox:</b><br/>"
            "&bull; <code>/me &lt;действие&gt;</code> - Физическое действие персонажа от 1-го лица<br/>"
            "&bull; <code>/do &lt;окружение&gt;</code> - Описание состояния обстановки или последствий<br/>"
            "&bull; <code>/try &lt;действие&gt;</code> - Действие с проверкой на удачу [Удачно / Неудачно]<br/>"
            "&bull; <code>/b &lt;текст&gt;</code> или <code>// &lt;текст&gt;</code> - Внеигровой чат (OOC)<br/>"
            "&bull; <code>/s &lt;текст&gt;</code> - Громкий крик<br/>"
            "&bull; <code>/c &lt;текст&gt;</code> - Тихий голос / шёпот<br/>"
            "&bull; <code>/clear</code> - Очистить окно сообщений у себя"
        )
        await sio.emit(
            "message",
            {
                "id": msg_id,
                "type": "system",
                "author": "Гид RP",
                "color": "#FFE066",
                "text": help_text,
                "timestamp": ts,
            },
            to=sid,
        )
        return

    # 2. Команда /clear (Очистка чата)
    if clean_text.lower() in ("/clear", "/очистить"):
        await sio.emit("clear_chat", {}, to=sid)
        return

    # 3. Команда /me (Действие персонажа)
    if clean_text.lower().startswith("/me "):
        action_content = clean_text[4:].strip()
        if not action_content:
            return
        payload = {
            "id": msg_id,
            "type": "me",
            "author": username,
            "role": role,
            "color": user_color,
            "text": action_content,
            "timestamp": ts,
        }

    # 4. Команда /do (Окружение и обстановка)
    elif clean_text.lower().startswith("/do "):
        do_content = clean_text[4:].strip()
        if not do_content:
            return
        payload = {
            "id": msg_id,
            "type": "do",
            "author": username,
            "role": role,
            "color": user_color,
            "text": do_content,
            "timestamp": ts,
        }

    # 5. Команда /try (Проверка удачи 50/50: Удачно или Неудачно)
    elif clean_text.lower().startswith("/try "):
        try_content = clean_text[5:].strip()
        if not try_content:
            return
        success = random.choice([True, False])
        result_label = "Удачно" if success else "Неудачно"
        payload = {
            "id": msg_id,
            "type": "try",
            "author": username,
            "role": role,
            "color": user_color,
            "text": try_content,
            "success": success,
            "result_text": result_label,
            "timestamp": ts,
        }

    # 6. Команда /b или // (Внеигровой OOC чат)
    elif (
        clean_text.lower().startswith("/b ")
        or clean_text.startswith("// ")
        or clean_text.lower().startswith("/ooc ")
    ):
        prefix_len = 3 if (clean_text.lower().startswith("/b ") or clean_text.startswith("// ")) else 5
        b_content = clean_text[prefix_len:].strip()
        if not b_content:
            return
        payload = {
            "id": msg_id,
            "type": "ooc",
            "author": username,
            "role": role,
            "color": user_color,
            "text": b_content,
            "timestamp": ts,
        }

    # 7. Команда /s (Крик)
    elif clean_text.lower().startswith("/s ") or clean_text.lower().startswith("/shout "):
        prefix_len = 3 if clean_text.lower().startswith("/s ") else 7
        shout_content = clean_text[prefix_len:].strip()
        if not shout_content:
            return
        payload = {
            "id": msg_id,
            "type": "shout",
            "author": username,
            "role": role,
            "color": user_color,
            "text": shout_content,
            "timestamp": ts,
        }

    # 8. Команда /c (Тихий голос / шёпот)
    elif (
        clean_text.lower().startswith("/c ")
        or clean_text.lower().startswith("/w ")
        or clean_text.lower().startswith("/whisper ")
    ):
        if clean_text.lower().startswith(("/c ", "/w ")):
            prefix_len = 3
        else:
            prefix_len = 9
        whisper_content = clean_text[prefix_len:].strip()
        if not whisper_content:
            return
        payload = {
            "id": msg_id,
            "type": "whisper",
            "author": username,
            "role": role,
            "color": user_color,
            "text": whisper_content,
            "timestamp": ts,
        }

    # 10. Стандартная внутриигровая IC речь
    else:
        payload = {
            "id": msg_id,
            "type": "chat",
            "author": username,
            "role": role,
            "color": user_color,
            "text": clean_text,
            "timestamp": ts,
        }

    # Сохраняем в историю комнаты и транслируем всем участникам
    if room_name in rooms:
        rooms[room_name]["history"].append(payload)
        if len(rooms[room_name]["history"]) > MAX_HISTORY_PER_ROOM:
            rooms[room_name]["history"].pop(0)

    await sio.emit("message", payload, room=room_name)


# HTTP-эндпоинты проверки состояния
async def handle_health(request: web.Request) -> web.Response:
    """Возвращает статус сервера, количество игроков и активных комнат."""
    return web.json_response(
        {
            "status": "healthy",
            "service": "Roblox RP External Overlay Server (Russian Edition)",
            "connected_clients": len(connected_users),
            "active_rooms": len(rooms),
            "rooms": [
                {"name": name, "members": len(data["members"])}
                for name, data in rooms.items()
            ],
            "server_time": get_current_timestamp(),
        }
    )


async def handle_index(request: web.Request) -> web.Response:
    """Информационная веб-страница сервера."""
    return web.Response(
        text=(
            "Сервер чат-оверлея Roblox RP активен и ожидает подключений!\n"
            f"Активных игроков онлайн: {len(connected_users)}\n"
            f"Активных комнат RP: {len(rooms)}\n"
            "Для запуска клиента выполните: python client.py\n"
        ),
        content_type="text/plain; charset=utf-8",
    )


app.router.add_get("/", handle_index)
app.router.add_get("/health", handle_health)


def main():
    parser = argparse.ArgumentParser(description="Сервер чат-оверлея Roblox RP")
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Хост привязки (по умолчанию: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="Порт сервера (по умолчанию: 5000)",
    )
    args = parser.parse_args()

    port = args.port
    max_attempts = 5
    for attempt in range(max_attempts):
        logger.info("=" * 65)
        logger.info(f"  Запуск сервера внешнего чат-оверлея Roblox RP...")
        logger.info(f"  Адрес: http://{args.host}:{port}")
        logger.info("  Готов принимать подключения клиентов оверлея")
        logger.info("=" * 65)

        try:
            web.run_app(app, host=args.host, port=port, print=None)
            break
        except OSError as e:
            if "10048" in str(e) or getattr(e, "errno", None) in (10048, 98):
                logger.warning(f"[ВНИМАНИЕ] Порт {port} уже занят другим процессом!")
                if attempt < max_attempts - 1:
                    port += 1
                    logger.info(f"Пробуем запустить на свободном порту {port}...")
                else:
                    logger.error("Не удалось найти свободный порт. Закройте предыдущие окна сервера и попробуйте снова.")
                    raise
            else:
                raise


if __name__ == "__main__":
    main()
