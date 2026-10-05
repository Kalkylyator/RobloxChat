#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Roblox RP Внешний Чат-Оверлей - Десктоп Клиент (PyQt5)
======================================================
Прозрачный, безрамочный оверлей для комфортной ролевой игры (RP) в Roblox.
Отображается поверх оконных игр и игр в режиме "окно без рамок" (Borderless).

Ключевые возможности:
- Режим "Всегда поверх всех окон" (Always-On-Top)
- Безрамочный стеклянный дизайн в аутентичном темном стиле Roblox
- Перетаскивание мышью и блокировка позиции клавишей (по умолчанию Ctrl+L)
- Глобальная горячая клавиша скрытия/показа (F3 или Ctrl+Shift+C)
- Мгновенный фокус ввода по нажатию '/' или Enter (снятие фокуса по Esc)
- Полная кастомизация: прозрачность, фон, размер шрифта, цвета команд /me, /do, /try
- Сохранение настроек в overlay_config.json
- Асинхронное подключение Socket.IO без зависания интерфейса (QThread)
"""

import html
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional

# Настройка кодировки и русского логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("RobloxOverlayClient")

# Подключение графической библиотеки: приоритет PyQt5, резерв PySide6
try:
    from PyQt5 import QtCore, QtGui, QtWidgets
    from PyQt5.QtCore import Qt, QPoint, pyqtSignal as Signal, QThread, QEasingCurve, QTimer
    from PyQt5.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QLineEdit, QTextBrowser, QPushButton, QLabel, QDialog,
        QSlider, QComboBox, QCheckBox, QSpinBox, QTabWidget,
        QSizeGrip, QColorDialog, QFileDialog, QFrame
    )
    from PyQt5.QtGui import QColor, QFont, QKeySequence, QIcon
except ImportError:
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
        from PySide6.QtCore import Qt, QPoint, Signal, QThread, QEasingCurve, QTimer
        from PySide6.QtWidgets import (
            QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
            QLineEdit, QTextBrowser, QPushButton, QLabel, QDialog,
            QSlider, QComboBox, QCheckBox, QSpinBox, QTabWidget,
            QSizeGrip, QColorDialog, QFileDialog, QFrame
        )
        from PySide6.QtGui import QColor, QFont, QKeySequence, QIcon
    except ImportError:
        print("[ОШИБКА] Не установлена библиотека PyQt5 или PySide6!")
        print("Выполните установку: pip install PyQt5 python-socketio websocket-client requests keyboard")
        sys.exit(1)

import socketio

def play_notification_sound(sound_path: str = ""):
    """
    Воспроизведение звукового уведомления о входящем сообщении.
    Поддерживает кастомный путь к аудиофайлу (.wav / .mp3 / .ogg) или системный звук по умолчанию.
    """
    sound_path = (sound_path or "").strip()
    if sound_path and os.path.isfile(sound_path):
        # 1. Попытка на Windows через встроенный MCI API (воспроизводит .mp3, .wav и др. без внешних библиотек)
        if sys.platform == "win32":
            try:
                import ctypes
                alias = "roblox_rp_notify"
                ctypes.windll.winmm.mciSendStringW(f'close {alias}', None, 0, None)
                open_cmd = f'open "{sound_path}" alias {alias}'
                res = ctypes.windll.winmm.mciSendStringW(open_cmd, None, 0, None)
                if res == 0:
                    ctypes.windll.winmm.mciSendStringW(f'play {alias} from 0', None, 0, None)
                    return
            except Exception as e:
                logger.debug(f"MCI Playback failed: {e}")

            # Резерв для .wav через стандартный winsound
            if sound_path.lower().endswith(".wav"):
                try:
                    import winsound
                    winsound.PlaySound(sound_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
                    return
                except Exception as e:
                    logger.debug(f"winsound error: {e}")

        # 2. Попытка через QtMultimedia QSound
        try:
            from PyQt5.QtMultimedia import QSound
            QSound.play(sound_path)
            return
        except Exception:
            pass

    # Звук по умолчанию (если файл не указан или недоступен)
    if sys.platform == "win32":
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
            return
        except Exception:
            pass

    try:
        QApplication.beep()
    except Exception:
        pass

# Попытка подключить библиотеку перехвата глобальных горячих клавиш (работает при активном окне игры)
HAS_KEYBOARD_LIB = False
try:
    import keyboard
    HAS_KEYBOARD_LIB = True
except Exception:
    HAS_KEYBOARD_LIB = False

# Файл локального сохранения конфигурации
CONFIG_FILE = "overlay_config.json"

# Конфигурация по умолчанию
DEFAULT_CONFIG = {
    # Сетевые параметры
    "server_url": "http://26.46.189.136:5000",
    "username": "Player_1",
    "room": "ROBLOX-RP-1",
    "role": "Гражданский",
    "user_color": "#5CABFF",

    # Внешний вид (стиль Roblox) и прозрачность
    "opacity": 0.85,
    "font_size": 13,
    "bg_color": "#191B1F",
    "text_color": "#FFFFFF",
    "show_timestamps": True,

    # Звуковые оповещения
    "sound_enabled": True,
    "sound_file": "",

    # Позиция отдельной кнопки Roblox
    "button_x": 30,
    "button_y": 30,

    # Цвета подсветки RP-команд
    "color_me": "#d8b4fe",        # Фиолетовый курсив для /me
    "color_do": "#38bdf8",        # Небесно-голубой для /do
    "color_try_success": "#4ade80", # Зеленый для [Удачно]
    "color_try_fail": "#f87171",  # Красный для [Неудачно]
    "color_ooc": "#94a3b8",       # Пепельно-серый для /b

    # Управление и горячие клавиши
    "hotkey_toggle": "f3",
    "hotkey_lock": "Ctrl+L",
    "locked": False,

    # Геометрия окна на экране
    "window_x": 40,
    "window_y": 60,
    "window_w": 480,
    "window_h": 360,
}

# Палитра готовых стильных цветов для быстрого выбора
COLOR_PRESETS = [
    ("#5CABFF", "Небесно-голубой"),
    ("#FF5C5C", "Алый"),
    ("#5CFF88", "Изумрудно-зеленый"),
    ("#FFB85C", "Янтарно-золотой"),
    ("#D97BFF", "Королевский фиолетовый"),
    ("#5CFFE6", "Бирюзовый бриз"),
    ("#FF7BC2", "Неоново-розовый"),
    ("#F8FAFC", "Белоснежный"),
]

# Список доступных глобальных клавиш
AVAILABLE_HOTKEYS = ["f3", "ctrl+shift+c", "f4", "f6", "f8", "f9", "f10"]
AVAILABLE_LOCK_HOTKEYS = ["Ctrl+L", "Ctrl+K", "Alt+L", "Ctrl+Shift+L"]


def load_config() -> Dict[str, Any]:
    """Загрузка сохраненных настроек из файла JSON."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                merged = {**DEFAULT_CONFIG, **data}
                return merged
        except Exception as e:
            logger.warning(f"Не удалось прочитать {CONFIG_FILE}: {e}")
    return DEFAULT_CONFIG.copy()


def save_config(cfg: Dict[str, Any]):
    """Запись текущих настроек в JSON-файл на диске."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Ошибка сохранения {CONFIG_FILE}: {e}")


# ==============================================================================
# Фоновый поток Socket.IO клиента (QThread)
# ==============================================================================
class SocketWorker(QThread):
    """
    Фоновый рабочий поток сетевого взаимодействия.
    Предотвращает любые подтормаживания или зависания графического интерфейса
    во время ожидания ответов сервера или переподключения.
    """
    connected = Signal()
    disconnected = Signal()
    joined_room = Signal(dict)
    message_received = Signal(dict)
    roster_updated = Signal(dict)
    clear_chat = Signal()
    error_occurred = Signal(str)

    def __init__(self, server_url: str, username: str, room: str, role: str, color: str):
        super().__init__()
        self.server_url = server_url
        self.username = username
        self.room = room
        self.role = role
        self.color = color
        self.sio = socketio.Client(reconnection=True, reconnection_delay=2, reconnection_attempts=15)
        self.is_running = True
        self._bind_events()

    def _bind_events(self):
        """Регистрация обработчиков сокет-событий."""
        @self.sio.event
        def connect():
            logger.info("Сокет-соединение с сервером успешно установлено.")
            self.connected.emit()
            # Автоматически отправляем запрос на вход в выбранную комнату
            self.sio.emit("join_room", {
                "username": self.username,
                "room": self.room,
                "role": self.role,
                "color": self.color,
            })

        @self.sio.event
        def disconnect():
            logger.info("Потеряно соединение с сервером. Попытка переподключения...")
            self.disconnected.emit()

        @self.sio.on("joined_success")
        def on_joined(data):
            self.joined_room.emit(data)

        @self.sio.on("message")
        def on_message(data):
            self.message_received.emit(data)

        @self.sio.on("room_roster")
        def on_roster(data):
            self.roster_updated.emit(data)

        @self.sio.on("clear_chat")
        def on_clear(data):
            self.clear_chat.emit()

        @self.sio.on("error_msg")
        def on_error(data):
            err_text = data.get("error", "Произошла непредвиденная ошибка на сервере")
            self.error_occurred.emit(err_text)

    def run(self):
        """Основной цикл потока."""
        try:
            self.sio.connect(self.server_url)
            self.sio.wait()
        except Exception as e:
            logger.error(f"Сбой подключения к серверу: {e}")
            self.error_occurred.emit(f"Не удалось подключиться к {self.server_url}: {str(e)}")
            self.disconnected.emit()

    def send_message(self, text: str):
        """Потокобезопасная отправка сообщения или RP-команды на сервер."""
        if self.sio and self.sio.connected:
            self.sio.emit("send_message", {"text": text})

    def update_user_info(self, username: str, room: str, role: str, color: str):
        """Обновление профиля игрока и смена комнаты без перезапуска приложения."""
        self.username = username
        self.room = room
        self.role = role
        self.color = color
        if self.sio and self.sio.connected:
            self.sio.emit("join_room", {
                "username": self.username,
                "room": self.room,
                "role": self.role,
                "color": self.color,
            })

    def stop(self):
        """Корректное завершение потока сокета без зависания процесса."""
        self.is_running = False
        try:
            # Отключаем автореконнект, чтобы сокет не пытался снова подключаться
            self.sio.reconnection = False
            # Безусловно вызываем disconnect, прерывая блокирующий sio.wait()
            self.sio.disconnect()
        except Exception as e:
            logger.debug(f"Ошибка при отключении сокета: {e}")
        self.quit()
        # Ожидаем завершения потока до 1 секунды
        if not self.wait(1000):
            logger.warning("Сетевой поток не завершился вовремя, принудительная остановка.")
            self.terminate()
            self.wait(200)


# ==============================================================================
# Расширенное Окно Настроек (SettingsDialog)
# ==============================================================================
class SettingsDialog(QDialog):
    """
    Полнофункциональное модальное окно настройки внешнего вида,
    параметров подключения, биндов и цветовой схемы RP-тегов.
    """
    settings_saved = Signal(dict)

    def __init__(self, parent=None, config: Optional[Dict[str, Any]] = None):
        super().__init__(parent)
        self.config = config.copy() if config else DEFAULT_CONFIG.copy()
        self.cur_user_color = self.config.get("user_color", "#5CABFF")
        self.setWindowTitle("Настройки Чат-Оверлея Roblox RP")
        self.setFixedSize(520, 600)
        self.setStyleSheet("""
            QDialog {
                background-color: #191B1F;
                color: #FFFFFF;
                font-family: 'Builder Sans', -apple-system, 'Segoe UI', Roboto, sans-serif;
            }
            QTabWidget::pane {
                border: 1px solid rgba(255, 255, 255, 0.08);
                background-color: #21252D;
                border-radius: 10px;
                padding: 14px;
            }
            QTabBar::tab {
                background: rgba(255, 255, 255, 0.06);
                color: #94A3B8;
                padding: 8px 18px;
                margin-right: 6px;
                border-radius: 8px;
                font-size: 12px;
                font-weight: bold;
            }
            QTabBar::tab:selected {
                background: #00A2FF;
                color: #FFFFFF;
            }
            QLabel {
                color: #CBD5E1;
                font-size: 12px;
                font-weight: 500;
            }
            QLineEdit, QComboBox, QSpinBox {
                background-color: #14161C;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                padding: 7px 12px;
                color: #FFFFFF;
                font-size: 12px;
            }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
                border: 1px solid #00A2FF;
                background-color: #181B23;
            }
            QPushButton {
                background-color: #00A2FF;
                color: white;
                border-radius: 8px;
                padding: 9px 20px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #008CE6;
            }
            QPushButton#btnCancel {
                background-color: rgba(255, 255, 255, 0.08);
                color: #CBD5E1;
                border: 1px solid rgba(255, 255, 255, 0.1);
            }
            QPushButton#btnCancel:hover {
                background-color: rgba(255, 255, 255, 0.15);
                color: #FFFFFF;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: rgba(255, 255, 255, 0.15);
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: #00A2FF;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #FFFFFF;
                border: 2px solid #00A2FF;
                width: 16px;
                margin-top: -5px;
                margin-bottom: -5px;
                border-radius: 8px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Заголовок окна настроек в стиле Roblox
        header_title = QLabel("ROBLOX RP • НАСТРОЙКИ")
        header_title.setStyleSheet("font-size: 14px; font-weight: 800; color: #FFFFFF; letter-spacing: 1px;")
        layout.addWidget(header_title)

        # Вкладки настроек: 1) Подключение и Профиль, 2) Внешний вид, 3) RP Теги и Бинды, 4) Звук
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self._build_tab_network()
        self._build_tab_appearance()
        self._build_tab_rp_tags()
        self._build_tab_sound()

        # --- Нижняя панель: Онлайн и Строка состояния сети (по запросу пользователя) ---
        parent_overlay = self.parent()
        is_conn = getattr(parent_overlay, "is_connected", False) if parent_overlay else False
        online_cnt = len(getattr(parent_overlay, "room_members", [])) if parent_overlay else 1
        srv_url = self.config.get("server_url", "http://26.46.189.136:5000")
        cur_room = self.config.get("room", "ROBLOX-RP-1")

        status_box = QFrame()
        status_box.setStyleSheet("""
            QFrame {
                background-color: rgba(18, 20, 25, 0.95);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 6px 10px;
            }
        """)
        sb_layout = QVBoxLayout(status_box)
        sb_layout.setContentsMargins(6, 6, 6, 6)
        sb_layout.setSpacing(4)

        row_top_sb = QHBoxLayout()
        dot_color = "#22C55E" if is_conn else "#EF4444"
        dot_text = "● Подключено к серверу" if is_conn else "● Нет связи с сервером"
        lbl_dot = QLabel(dot_text)
        lbl_dot.setStyleSheet(f"color: {dot_color}; font-weight: bold; font-size: 11px;")

        lbl_online = QLabel(f"👥 Онлайн в комнате: {online_cnt} чел.")
        lbl_online.setStyleSheet("color: #60A5FA; font-weight: bold; font-size: 11px;")

        row_top_sb.addWidget(lbl_dot)
        row_top_sb.addStretch()
        row_top_sb.addWidget(lbl_online)
        sb_layout.addLayout(row_top_sb)

        lbl_state = QLabel(f"Строка состояния: Сервер: {srv_url} | Канал: [{cur_room}]")
        lbl_state.setStyleSheet("color: #94A3B8; font-size: 10px;")
        sb_layout.addWidget(lbl_state)

        layout.addWidget(status_box)

        # Нижняя панель с кнопками Сохранить / Отмена
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_cancel = QPushButton("Отмена")
        btn_cancel.setObjectName("btnCancel")
        btn_cancel.clicked.connect(self.reject)

        btn_save = QPushButton("Сохранить и Применить")
        btn_save.clicked.connect(self.on_save)

        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_save)
        layout.addLayout(btn_layout)

    def _build_tab_network(self):
        """Вкладка 1: Параметры сервера и игрового профиля."""
        tab = QWidget()
        l = QVBoxLayout(tab)
        l.setSpacing(10)

        # Адрес сервера (Radmin / Localhost / Cloud)
        l.addWidget(QLabel("Адрес сервера (Socket.IO / Radmin VPN):"))
        self.inp_server = QLineEdit(self.config.get("server_url", "http://26.46.189.136:5000"))
        self.inp_server.setPlaceholderText("например: http://26.154.32.10:5000 или http://localhost:5000")
        l.addWidget(self.inp_server)

        # Никнейм персонажа на английском языке
        l.addWidget(QLabel("Имя персонажа / Никнейм (на английском языке):"))
        self.inp_user = QLineEdit(self.config.get("username", "Player_1"))
        self.inp_user.setPlaceholderText("например: Officer_John, Blox_R, Cole_99")
        l.addWidget(self.inp_user)

        # Приватная комната
        l.addWidget(QLabel("Код комнаты (RP-канал):"))
        self.inp_room = QLineEdit(self.config.get("room", "ROBLOX-RP-1"))
        l.addWidget(self.inp_room)

        # Роль / Позывной / Фракция
        l.addWidget(QLabel("Роль / Позывной (например: Полиция LSPD, Скорая EMS, Гражданский):"))
        self.inp_role = QLineEdit(self.config.get("role", "Гражданский"))
        l.addWidget(self.inp_role)

        # Выбор цвета ника (Готовые пресеты + Произвольная RGB палитра)
        l.addWidget(QLabel("Цвет никнейма в чате (RGB / Пресеты):"))
        color_row = QHBoxLayout()
        self.combo_user_color = QComboBox()
        for hex_code, name in COLOR_PRESETS:
            self.combo_user_color.addItem(f"{name} ({hex_code})", hex_code)

        # Проверяем, есть ли цвет в пресетах
        found = False
        for i in range(self.combo_user_color.count()):
            if self.combo_user_color.itemData(i).upper() == self.cur_user_color.upper():
                self.combo_user_color.setCurrentIndex(i)
                found = True
                break
        if not found:
            self.combo_user_color.insertItem(0, f"RGB: {self.cur_user_color}", self.cur_user_color)
            self.combo_user_color.setCurrentIndex(0)

        self.btn_pick_rgb = QPushButton("🎨 Выбрать RGB")
        self.btn_pick_rgb.setToolTip("Открыть палитру для выбора любого RGB оттенка")
        self.btn_pick_rgb.setStyleSheet("background-color: #374151; padding: 6px 12px;")
        self.btn_pick_rgb.clicked.connect(self._open_rgb_picker)

        self.lbl_color_badge = QLabel("     ")
        self.lbl_color_badge.setFixedSize(30, 26)
        self._update_color_badge()

        self.combo_user_color.currentIndexChanged.connect(self._on_preset_color_changed)

        color_row.addWidget(self.combo_user_color, stretch=1)
        color_row.addWidget(self.btn_pick_rgb)
        color_row.addWidget(self.lbl_color_badge)
        l.addLayout(color_row)

        l.addStretch()
        self.tabs.addTab(tab, "Профиль и Сеть")

    def _open_rgb_picker(self):
        col = QColorDialog.getColor(QColor(self.cur_user_color), self, "Выберите RGB цвет никнейма")
        if col.isValid():
            self.cur_user_color = col.name().upper()
            self.combo_user_color.insertItem(0, f"RGB: {self.cur_user_color}", self.cur_user_color)
            self.combo_user_color.setCurrentIndex(0)
            self._update_color_badge()

    def _on_preset_color_changed(self, idx):
        data = self.combo_user_color.currentData()
        if data:
            self.cur_user_color = data
            self._update_color_badge()

    def _update_color_badge(self):
        self.lbl_color_badge.setStyleSheet(
            f"background-color: {self.cur_user_color}; border: 2px solid #FFFFFF; border-radius: 6px;"
        )

    def _build_tab_appearance(self):
        """Вкладка 2: Настройка прозрачности, шрифта и отображения в стиле Roblox."""
        tab = QWidget()
        l = QVBoxLayout(tab)
        l.setSpacing(12)

        # Ползунок прозрачности окна
        self.lbl_opacity = QLabel(f"Прозрачность фона окна: {int(self.config.get('opacity', 0.85) * 100)}%")
        l.addWidget(self.lbl_opacity)
        self.slider_opacity = QSlider(Qt.Horizontal)
        self.slider_opacity.setRange(15, 100)
        self.slider_opacity.setValue(int(self.config.get("opacity", 0.85) * 100))
        self.slider_opacity.valueChanged.connect(
            lambda v: self.lbl_opacity.setText(f"Прозрачность фона окна: {v}%")
        )
        l.addWidget(self.slider_opacity)

        # Размер шрифта
        row_font = QHBoxLayout()
        row_font.addWidget(QLabel("Размер шрифта сообщений (px):"))
        self.spin_font = QSpinBox()
        self.spin_font.setRange(10, 22)
        self.spin_font.setValue(int(self.config.get("font_size", 13)))
        row_font.addWidget(self.spin_font)
        l.addLayout(row_font)

        # Выбор фонового оттенка
        l.addWidget(QLabel("Основной цвет подложки чата:"))
        self.combo_bg_color = QComboBox()
        self.combo_bg_color.addItem("Классический Roblox Dark (#191B1F)", "#191B1F")
        self.combo_bg_color.addItem("Глубокий чернильный (#111317)", "#111317")
        self.combo_bg_color.addItem("Темно-синий Navy (#141923)", "#141923")
        self.combo_bg_color.addItem("Угольно-серый Slate (#1E222B)", "#1E222B")
        cur_bg = self.config.get("bg_color", "#191B1F")
        for i in range(self.combo_bg_color.count()):
            if self.combo_bg_color.itemData(i) == cur_bg:
                self.combo_bg_color.setCurrentIndex(i)
                break
        l.addWidget(self.combo_bg_color)

        # Отображение времени сообщений
        self.chk_timestamps = QCheckBox("Отображать время сообщений [ЧЧ:ММ:СС]")
        self.chk_timestamps.setChecked(self.config.get("show_timestamps", True))
        self.chk_timestamps.setStyleSheet("color: #E2E8F0; font-size: 12px;")
        l.addWidget(self.chk_timestamps)

        # Подсказка про открытие по нажатию клавиши '/'
        lbl_slash_hint = QLabel("⌨️ Чтобы начать писать в чат, нажмите клавишу '/' на клавиатуре или кликните в поле ввода.")
        lbl_slash_hint.setStyleSheet("color: #94A3B8; font-size: 11px; margin-top: 4px;")
        l.addWidget(lbl_slash_hint)

        l.addStretch()
        self.tabs.addTab(tab, "Внешний вид и Оформление")

    def _build_tab_rp_tags(self):
        """Вкладка 3: Горячие клавиши и цвета RP-команд (/me, /do, /try)."""
        tab = QWidget()
        l = QVBoxLayout(tab)
        l.setSpacing(10)

        # Горячая клавиша скрытия оверлея
        l.addWidget(QLabel("Глобальная клавиша скрыть/показать (работает поверх игры):"))
        self.combo_hotkey = QComboBox()
        for hk in AVAILABLE_HOTKEYS:
            self.combo_hotkey.addItem(hk.upper(), hk)
        cur_hk = self.config.get("hotkey_toggle", "f3").lower()
        idx_hk = self.combo_hotkey.findData(cur_hk)
        if idx_hk >= 0:
            self.combo_hotkey.setCurrentIndex(idx_hk)
        l.addWidget(self.combo_hotkey)

        # Горячая клавиша блокировки перетаскивания
        l.addWidget(QLabel("Бинды блокировки позиции окна (Lock Drag):"))
        self.combo_lock_hk = QComboBox()
        for lhk in AVAILABLE_LOCK_HOTKEYS:
            self.combo_lock_hk.addItem(lhk, lhk)
        cur_lhk = self.config.get("hotkey_lock", "Ctrl+L")
        idx_lhk = self.combo_lock_hk.findData(cur_lhk)
        if idx_lhk >= 0:
            self.combo_lock_hk.setCurrentIndex(idx_lhk)
        l.addWidget(self.combo_lock_hk)

        # Цвета подсветки RP команд
        l.addWidget(QLabel("Цвет подсветки действий /me:"))
        self.inp_col_me = QLineEdit(self.config.get("color_me", "#d8b4fe"))
        l.addWidget(self.inp_col_me)

        l.addWidget(QLabel("Цвет описания обстановки /do:"))
        self.inp_col_do = QLineEdit(self.config.get("color_do", "#38bdf8"))
        l.addWidget(self.inp_col_do)

        l.addWidget(QLabel("Цвет успешного исхода /try [УСПЕХ]:"))
        self.inp_col_try_s = QLineEdit(self.config.get("color_try_success", "#4ade80"))
        l.addWidget(self.inp_col_try_s)

        l.addWidget(QLabel("Цвет провального исхода /try [ПРОВАЛ]:"))
        self.inp_col_try_f = QLineEdit(self.config.get("color_try_fail", "#f87171"))
        l.addWidget(self.inp_col_try_f)

        l.addStretch()
        self.tabs.addTab(tab, "Клавиши и RP Теги")

    def _build_tab_sound(self):
        """Вкладка 4: Настройка звуковых уведомлений чата."""
        tab = QWidget()
        l = QVBoxLayout(tab)
        l.setSpacing(12)

        # Чекбокс включения звука
        self.chk_sound_enabled = QCheckBox("Включить звуковые уведомления о сообщениях")
        self.chk_sound_enabled.setChecked(self.config.get("sound_enabled", True))
        self.chk_sound_enabled.setStyleSheet("color: #FFFFFF; font-weight: bold; font-size: 13px;")
        l.addWidget(self.chk_sound_enabled)

        lbl_desc = QLabel(
            "🔔 Свои сообщения не озвучиваются — звук воспроизводится только при получении сообщений от других игроков."
        )
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet("color: #94A3B8; font-size: 11px;")
        l.addWidget(lbl_desc)

        # Выбор своего звукового файла
        l.addWidget(QLabel("Кастомный звуковой файл (оставьте пустым для звука по умолчанию):"))
        file_row = QHBoxLayout()
        self.inp_sound_file = QLineEdit(self.config.get("sound_file", ""))
        self.inp_sound_file.setPlaceholderText("Путь к файлу .wav / .mp3 или нажмите 'Обзор...'")

        btn_browse_sound = QPushButton("📁 Обзор...")
        btn_browse_sound.setStyleSheet("background-color: #374151; padding: 6px 12px; font-weight: bold;")
        btn_browse_sound.clicked.connect(self._browse_sound_file)

        file_row.addWidget(self.inp_sound_file, stretch=1)
        file_row.addWidget(btn_browse_sound)
        l.addLayout(file_row)

        # Кнопки прослушивания и сброса
        actions_row = QHBoxLayout()
        btn_test_sound = QPushButton("▶ Прослушать звук")
        btn_test_sound.setStyleSheet("background-color: #00A2FF; color: white; padding: 6px 14px; font-weight: bold;")
        btn_test_sound.clicked.connect(self._test_sound)

        btn_reset_sound = QPushButton("Сбросить на стандартный")
        btn_reset_sound.setStyleSheet("background-color: #4B5563; padding: 6px 12px;")
        btn_reset_sound.clicked.connect(lambda: self.inp_sound_file.clear())

        actions_row.addWidget(btn_test_sound)
        actions_row.addWidget(btn_reset_sound)
        actions_row.addStretch()
        l.addLayout(actions_row)

        l.addStretch()
        self.tabs.addTab(tab, "Звук и Уведомления")

    def _browse_sound_file(self):
        fpath, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите звуковой файл уведомления",
            "",
            "Аудио файлы (*.wav *.mp3 *.ogg);;Все файлы (*.*)"
        )
        if fpath:
            self.inp_sound_file.setText(fpath)

    def _test_sound(self):
        path = self.inp_sound_file.text().strip()
        play_notification_sound(path)

    def on_save(self):
        """Сбор всех данных и передача сигнала сохранения."""
        new_cfg = self.config.copy()
        new_cfg["server_url"] = self.inp_server.text().strip() or "http://26.46.189.136:5000"

        # Фильтрация никнейма: только английские буквы, цифры и символы _ -
        raw_user = self.inp_user.text().strip()
        clean_user = "".join(c for c in raw_user if c.isascii() and (c.isalnum() or c in ("_", "-"))) or "Player_1"
        new_cfg["username"] = clean_user

        new_cfg["room"] = self.inp_room.text().strip().upper() or "ROBLOX-RP-1"
        new_cfg["role"] = self.inp_role.text().strip() or "Гражданский"
        new_cfg["user_color"] = self.cur_user_color

        new_cfg["opacity"] = self.slider_opacity.value() / 100.0
        new_cfg["font_size"] = self.spin_font.value()
        new_cfg["bg_color"] = self.combo_bg_color.currentData()
        new_cfg["show_timestamps"] = self.chk_timestamps.isChecked()

        new_cfg["hotkey_toggle"] = self.combo_hotkey.currentData()
        new_cfg["hotkey_lock"] = self.combo_lock_hk.currentData()

        new_cfg["color_me"] = self.inp_col_me.text().strip() or "#d8b4fe"
        new_cfg["color_do"] = self.inp_col_do.text().strip() or "#38bdf8"
        new_cfg["color_try_success"] = self.inp_col_try_s.text().strip() or "#4ade80"
        new_cfg["color_try_fail"] = self.inp_col_try_f.text().strip() or "#f87171"

        new_cfg["sound_enabled"] = self.chk_sound_enabled.isChecked()
        new_cfg["sound_file"] = self.inp_sound_file.text().strip()

        self.settings_saved.emit(new_cfg)
        self.accept()


# ==============================================================================
# Отдельная Подвижная Кнопка Чата (RobloxFloatingButton)
# ==============================================================================
class RobloxFloatingButton(QWidget):
    """
    Отдельная перемещаемая кнопка в точном стиле Roblox CoreGui (💬).
    Её можно свободно перетаскивать мышью в любое место экрана.
    Клик по ней открывает/закрывает окно чата.
    """
    def __init__(self, overlay: "RobloxChatOverlay"):
        super().__init__()
        self.overlay = overlay
        self.is_dragging = False
        self.drag_position = QPoint()
        self.has_moved = False

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(42, 42)

        # Восстановление сохраненных экранных координат кнопки
        bx = self.overlay.config.get("button_x", 30)
        by = self.overlay.config.get("button_y", 30)
        self.move(bx, by)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.button = QPushButton("💬", self)
        self.button.setFixedSize(42, 42)
        self.button.setCursor(Qt.PointingHandCursor)
        self.button.setToolTip(
            "Чат Roblox RP\n"
            "• Перетащите мышью в любое удобное место экрана\n"
            "• Нажмите, чтобы открыть или скрыть окно чата\n"
            "• Или нажмите клавишу / на клавиатуре"
        )
        self.update_button_style(is_open=self.overlay.isVisible())
        self.button.clicked.connect(self.on_button_clicked)
        layout.addWidget(self.button)

    def update_button_style(self, is_open: bool):
        if is_open:
            self.button.setStyleSheet("""
                QPushButton {
                    background-color: rgba(30, 35, 45, 0.95);
                    color: #FFFFFF;
                    border: 2px solid #00A2FF;
                    border-radius: 10px;
                    font-size: 17px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: rgba(45, 55, 75, 0.98);
                }
            """)
        else:
            self.button.setStyleSheet("""
                QPushButton {
                    background-color: rgba(22, 25, 30, 0.88);
                    color: #CBD5E1;
                    border: 1px solid rgba(255, 255, 255, 0.2);
                    border-radius: 10px;
                    font-size: 17px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: rgba(40, 45, 55, 0.98);
                    color: #FFFFFF;
                    border: 1px solid rgba(255, 255, 255, 0.4);
                }
            """)

    def on_button_clicked(self):
        if self.has_moved:
            self.has_moved = False
            return
        self.overlay.toggle_visibility_from_button()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.is_dragging = True
            self.has_moved = False
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self.is_dragging:
            delta = (event.globalPos() - self.frameGeometry().topLeft()) - self.drag_position
            if abs(delta.x()) > 2 or abs(delta.y()) > 2:
                self.has_moved = True
            self.move(event.globalPos() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        if self.is_dragging:
            self.is_dragging = False
            self.overlay.config["button_x"] = self.x()
            self.overlay.config["button_y"] = self.y()
            save_config(self.overlay.config)
            event.accept()


# ==============================================================================
# Главное Окно Прозрачного Оверлея (RobloxChatOverlay)
# ==============================================================================
class RobloxChatOverlay(QMainWindow):
    """
    Основное безрамочное полупрозрачное окно оверлея.
    Отображается поверх оконных игр и обеспечивает мгновенный отклик на нажатия клавиш.
    """
    def __init__(self):
        super().__init__()
        self.config = load_config()

        # Состояния мыши и окна
        self.is_dragging = False
        self.drag_position = QPoint()
        self.is_locked = self.config.get("locked", False)
        self.is_minimized_mode = False
        self.is_click_through = False
        self.btn_lock = None
        self.btn_fold = None
        self.btn_ct = None
        self.status_dot = None
        self.roster_badge = None
        self.registered_hooks: List[Any] = []

        # Состояние подключения
        self.is_connected = False

        # Буфер истории введенных команд для стрелок Вверх/Вниз
        self.cmd_history: List[str] = []
        self.cmd_history_idx = -1

        # Список участников комнаты
        self.room_members: List[dict] = []

        self.init_window_flags()
        self.init_ui()

        # Создаем и отображаем отдельную подвижную кнопку чата в стиле Roblox
        self.floating_btn = RobloxFloatingButton(self)
        self.floating_btn.show()

        self.init_socket_worker()
        self.init_global_hotkeys()

    def init_window_flags(self):
        """
        Установка флагов окна:
        - FramelessWindowHint: убирает стандартную рамку ОС Windows
        - WindowStaysOnTopHint: режим "Всегда поверх всех окон"
        - Tool / SubWindow: не перекрывает системный фокус
        - WA_TranslucentBackground: истинная прозрачность фона
        """
        flags = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, False)

        # Восстановление сохраненных экранных координат и размеров
        x = self.config.get("window_x", 40)
        y = self.config.get("window_y", 60)
        w = self.config.get("window_w", 480)
        h = self.config.get("window_h", 360)
        self.setGeometry(x, y, w, h)
        self.setMinimumSize(320, 200)

    def init_ui(self):
        """Построение интерфейса в точном стиле Roblox."""
        self.central_widget = QWidget(self)
        self.setCentralWidget(self.central_widget)

        # Основной контейнер с настраиваемым фоном и скругленными углами
        self.main_frame = QWidget(self.central_widget)
        self.main_frame.setObjectName("mainFrame")
        self.update_style_sheet()

        master_layout = QVBoxLayout(self.central_widget)
        master_layout.setContentsMargins(4, 4, 4, 4)
        master_layout.addWidget(self.main_frame)

        frame_layout = QVBoxLayout(self.main_frame)
        frame_layout.setContentsMargins(10, 8, 10, 8)
        frame_layout.setSpacing(6)

        # --- Верхняя панель заголовка (Header) ---
        # По запросу: только название комнаты и кнопка настроек (без кнопки чата)
        header = QWidget()
        header.setFixedHeight(28)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(4, 0, 4, 0)
        header_layout.setSpacing(8)

        # Название комнаты
        cur_room = self.config.get('room', 'ROBLOX-RP-1')
        self.title_label = QLabel(f"[{cur_room}]")
        self.title_label.setStyleSheet("color: #94A3B8; font-weight: bold; font-size: 12px; letter-spacing: 0.5px;")

        # Кнопка Настроек (Шестеренка) рядом с названием комнаты
        self.btn_settings = QPushButton("⚙")
        self.btn_settings.setFixedSize(22, 22)
        self.btn_settings.setToolTip("Параметры чата, онлайн и строка состояния")
        self.btn_settings.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.08);
                color: #CBD5E1;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.2);
                color: #FFFFFF;
            }
        """)
        self.btn_settings.clicked.connect(self.open_settings)

        header_layout.addWidget(self.title_label)
        header_layout.addWidget(self.btn_settings)
        header_layout.addStretch()

        frame_layout.addWidget(header)

        # --- Область сообщений чата (QTextBrowser) ---
        self.chat_browser = QTextBrowser()
        self.chat_browser.setOpenExternalLinks(False)
        self.chat_browser.setReadOnly(True)
        self.update_chat_font_style()
        frame_layout.addWidget(self.chat_browser, stretch=1)

        # --- Нижняя панель ввода текста (Input Bar в стиле Roblox) ---
        self.input_container = QWidget(self.main_frame)
        self.input_container.setFixedHeight(34)
        input_layout = QHBoxLayout(self.input_container)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(6)

        # Поле ввода в точном визуальном стиле Roblox (как на фото)
        input_box = QWidget(self.input_container)
        input_box.setStyleSheet("""
            QWidget {
                background-color: rgba(20, 23, 28, 0.9);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 8px;
            }
        """)
        ib_layout = QHBoxLayout(input_box)
        ib_layout.setContentsMargins(10, 2, 6, 2)
        ib_layout.setSpacing(4)

        self.input_field = QLineEdit(input_box)
        self.input_field.setPlaceholderText("To chat click here or press / key")
        self.input_field.setStyleSheet("""
            QLineEdit {
                background: transparent;
                border: none;
                color: #FFFFFF;
                font-size: 12px;
                selection-background-color: #3B82F6;
            }
        """)
        self.input_field.returnPressed.connect(self.send_chat_message)

        # Иконка отправки сообщения
        self.btn_send = QPushButton("➤", input_box)
        self.btn_send.setFixedSize(24, 24)
        self.btn_send.setToolTip("Отправить сообщение (Enter)")
        self.btn_send.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #94A3B8;
                font-size: 13px;
            }
            QPushButton:hover {
                color: #FFFFFF;
            }
        """)
        self.btn_send.clicked.connect(self.send_chat_message)

        ib_layout.addWidget(self.input_field, stretch=1)
        ib_layout.addWidget(self.btn_send)

        # Быстрые RP кнопки (/me, /try, /b)
        self.btn_me_shortcut = QPushButton("/me", self.input_container)
        self.btn_me_shortcut.setFixedSize(34, 30)
        self.btn_me_shortcut.setToolTip("Быстро вставить действие /me")
        self.btn_me_shortcut.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.08);
                color: #D8B4FE;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 6px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(216, 180, 254, 0.25);
            }
        """)
        self.btn_me_shortcut.clicked.connect(lambda: self.insert_command_prefix("/me "))

        self.btn_try_shortcut = QPushButton("/try", self.input_container)
        self.btn_try_shortcut.setFixedSize(36, 30)
        self.btn_try_shortcut.setToolTip("Быстро вставить действие удачи /try [Удачно / Неудачно]")
        self.btn_try_shortcut.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.08);
                color: #86EFAC;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 6px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(134, 239, 172, 0.25);
            }
        """)
        self.btn_try_shortcut.clicked.connect(lambda: self.insert_command_prefix("/try "))

        self.btn_b_shortcut = QPushButton("/b", self.input_container)
        self.btn_b_shortcut.setFixedSize(32, 30)
        self.btn_b_shortcut.setToolTip("Быстро вставить внеигровой чат /b")
        self.btn_b_shortcut.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.08);
                color: #94A3B8;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 6px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(148, 163, 184, 0.25);
            }
        """)
        self.btn_b_shortcut.clicked.connect(lambda: self.insert_command_prefix("/b "))

        self.size_grip = QSizeGrip(self.input_container)
        self.size_grip.setFixedSize(14, 14)
        self.size_grip.setStyleSheet("background: transparent;")

        input_layout.addWidget(input_box, stretch=1)
        input_layout.addWidget(self.btn_me_shortcut)
        input_layout.addWidget(self.btn_try_shortcut)
        input_layout.addWidget(self.btn_b_shortcut)
        input_layout.addWidget(self.size_grip)

        frame_layout.addWidget(self.input_container)

        # Приветственное системное сообщение
        hk_name = self.config.get("hotkey_toggle", "f3").upper()
        self.append_system_html(
            f"<b>[Система]:</b> Чат-оверлей Roblox RP готов к работе. Канал: <b>{self.config.get('room', 'RP')}</b>.<br/>"
            f"• Нажмите <code>/</code> для набора, <code>/help</code> для списка команд. Нажмите <b>{hk_name}</b>, чтобы скрыть/показать."
        )

    def update_style_sheet(self):
        """Обновление полупрозрачного фона и границ."""
        opacity = self.config.get("opacity", 0.85)
        alpha = int(opacity * 255)
        hex_bg = self.config.get("bg_color", "#191B1F").lstrip("#")
        try:
            r = int(hex_bg[0:2], 16)
            g = int(hex_bg[2:4], 16)
            b = int(hex_bg[4:6], 16)
        except Exception:
            r, g, b = 25, 27, 31

        self.main_frame.setStyleSheet(f"""
            QWidget#mainFrame {{
                background-color: rgba({r}, {g}, {b}, {alpha});
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 10px;
            }}
        """)

    def update_chat_font_style(self):
        """Обновление шрифта и полосы прокрутки сообщений."""
        font_sz = self.config.get("font_size", 13)
        self.chat_browser.setStyleSheet(f"""
            QTextBrowser {{
                background: transparent;
                border: none;
                color: #FFFFFF;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                font-size: {font_sz}px;
                line-height: 1.4;
            }}
            QScrollBar:vertical {{
                border: none;
                background: rgba(0, 0, 0, 0.2);
                width: 6px;
                border-radius: 3px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(255, 255, 255, 0.25);
                border-radius: 3px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: rgba(255, 255, 255, 0.45);
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """)

    def init_socket_worker(self):
        """Запуск фонового сетевого потока."""
        self.worker = SocketWorker(
            server_url=self.config.get("server_url", "http://26.46.189.136:5000"),
            username=self.config.get("username", "Игрок_1"),
            room=self.config.get("room", "ROBLOX-RP-1"),
            role=self.config.get("role", "Гражданский"),
            color=self.config.get("user_color", "#5CABFF"),
        )
        self.worker.connected.connect(self.on_socket_connected)
        self.worker.disconnected.connect(self.on_socket_disconnected)
        self.worker.joined_room.connect(self.on_joined_room)
        self.worker.message_received.connect(self.on_message_received)
        self.worker.roster_updated.connect(self.on_roster_updated)
        self.worker.clear_chat.connect(self.on_clear_chat)
        self.worker.error_occurred.connect(self.on_socket_error)
        self.worker.start()

    def set_click_through(self, enabled: bool):
        pass

    def toggle_click_through_manual(self):
        pass

    def toggle_visibility_from_button(self):
        pass

    def toggle_visibility_from_global(self):
        """Переключение видимости по хоткею (F3)."""
        self.toggle_visibility_from_button()

    def activate_chat_input(self, prefix: str = ""):
        """Быстрый захват ввода: пробуждение оверлея, показ окна при необходимости и фокус."""
        if getattr(self, "is_click_through", False):
            self.set_click_through(False)

        if not self.isVisible():
            self.show()

        self.raise_()
        self.activateWindow()

        if hasattr(self, "floating_btn") and self.floating_btn:
            self.floating_btn.update_button_style(is_open=True)

        if prefix:
            self.input_field.setText(prefix)
            self.input_field.setCursorPosition(len(prefix))
        else:
            self.input_field.clear()

        self.input_field.setFocus()

    def deactivate_chat_input(self):
        """Освобождение ввода и возврат в игровой режим при необходимости."""
        self.input_field.clearFocus()
        if self.config.get("click_through", False):
            self.set_click_through(True)

    def init_global_hotkeys(self):
        """Регистрация глобальных горячих клавиш перехвата (F3, T, /)."""
        if not HAS_KEYBOARD_LIB:
            logger.info("Библиотека keyboard недоступна. Используются локальные клавиши окна.")
            return

        # Безопасно снимаем только ранее зарегистрированные хуки этого приложения
        for h in self.registered_hooks:
            try:
                keyboard.remove_hotkey(h)
            except Exception:
                pass
        self.registered_hooks.clear()

        hotkey = self.config.get("hotkey_toggle", "f3").lower()
        try:
            h_toggle = keyboard.add_hotkey(hotkey, self.toggle_visibility_from_global)
            self.registered_hooks.append(h_toggle)
            logger.info(f"Глобальная горячая клавиша '{hotkey}' успешно зарегистрирована.")

            # Если активирован быстрый фокус чата по клавишам / и T
            if self.config.get("fast_focus_keys", True):
                try:
                    h_slash = keyboard.add_hotkey("/", self.trigger_fast_focus_slash, suppress=False)
                    self.registered_hooks.append(h_slash)
                    logger.info("Глобальный быстрый фокус по клавише '/' активирован.")
                except Exception as e:
                    logger.debug(f"Не удалось привязать глобальную '/': {e}")

        except (ImportError, PermissionError, OSError) as e:
            logger.warning(f"Нет прав на глобальный перехват клавиши '{hotkey}' (рекомендуется запуск от имени Администратора): {e}")
        except Exception as e:
            logger.warning(f"Не удалось перехватить глобальную клавишу '{hotkey}': {e}")

    def trigger_fast_focus_t(self):
        """Потокобезопасный сигнал активации чата по 'T' из потока перехвата keyboard."""
        QtCore.QMetaObject.invokeMethod(self, "global_activate_t", Qt.QueuedConnection)

    def trigger_fast_focus_slash(self):
        """Потокобезопасный сигнал активации чата по '/' из потока перехвата keyboard."""
        QtCore.QMetaObject.invokeMethod(self, "global_activate_slash", Qt.QueuedConnection)

    @QtCore.pyqtSlot()
    def global_activate_t(self):
        self.activate_chat_input(prefix="")

    @QtCore.pyqtSlot()
    def global_activate_slash(self):
        self.activate_chat_input(prefix="/")

    def toggle_visibility_from_global(self):
        """Потокобезопасный вызов переключения видимости из отдельного хук-потока."""
        QtCore.QMetaObject.invokeMethod(self, "toggle_overlay_visibility", Qt.QueuedConnection)

    @QtCore.pyqtSlot()
    def toggle_overlay_visibility(self):
        """Скрыть или показать оверлей."""
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()

    def toggle_collapse(self):
        """Сворачивание чата в компактную строку заголовка и обратно."""
        if not self.is_minimized_mode:
            self.chat_browser.hide()
            self.input_container.hide()
            self.setMinimumHeight(44)
            self.setMaximumHeight(44)
            self.resize(self.width(), 44)
            if hasattr(self, "btn_fold") and self.btn_fold:
                self.btn_fold.setText("□")
                self.btn_fold.setToolTip("Развернуть чат")
            self.is_minimized_mode = True
        else:
            self.setMinimumHeight(200)
            self.setMaximumHeight(16777215)
            self.chat_browser.show()
            self.input_container.show()
            saved_w = self.config.get("window_w", 480)
            saved_h = self.config.get("window_h", 390)
            self.resize(saved_w, saved_h)
            if hasattr(self, "btn_fold") and self.btn_fold:
                self.btn_fold.setText("—")
                self.btn_fold.setToolTip("Свернуть чат в компактную строку")
            self.is_minimized_mode = False

    def toggle_lock(self):
        """Блокировка и разблокировка перетаскивания окна."""
        self.is_locked = not self.is_locked
        if hasattr(self, "btn_lock") and self.btn_lock:
            self.btn_lock.setText("🔒" if self.is_locked else "🔓")
        self.config["locked"] = self.is_locked
        save_config(self.config)
        status_txt = "заблокировано" if self.is_locked else "разблокировано"
        self.append_system_html(f"<i>Перемещение окна {status_txt} (Ctrl+L).</i>")

    def insert_command_prefix(self, prefix: str):
        """Вставка префикса команды в строку ввода с установкой курсора в конец."""
        self.input_field.setText(prefix)
        self.input_field.setFocus()
        self.input_field.setCursorPosition(len(prefix))

    # --- Перетаскивание окна мышью ---
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self.is_locked:
            self.is_dragging = True
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self.is_dragging and not self.is_locked:
            self.move(event.globalPos() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        if self.is_dragging:
            self.is_dragging = False
            self.config["window_x"] = self.x()
            self.config["window_y"] = self.y()
            save_config(self.config)
            event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self.is_minimized_mode:
            self.config["window_w"] = self.width()
            self.config["window_h"] = self.height()
            save_config(self.config)

    # --- Управление клавиатурой и перехват клавиш ---
    def keyPressEvent(self, event):
        # Нажатие '/' или Enter активирует строку чата для набора.
        # Поддерживается как английская раскладка ('/'), так и русская (где на физической клавише слэша находится '.')
        # а также цифровая клавиатура (NumPad) и сканкоды клавиши слэша
        is_slash_trigger = (
            event.key() in (Qt.Key_Slash, Qt.Key_Backslash)
            or event.text() in ("/", "?")
            or (event.key() == Qt.Key_Period and event.modifiers() == Qt.NoModifier)
            or (getattr(event, "nativeVirtualKey", lambda: 0)() == 0xBF and event.modifiers() == Qt.NoModifier)
        )

        if not self.input_field.hasFocus():
            if is_slash_trigger:
                self.activate_chat_input(prefix="/")
                event.accept()
                return
            elif event.key() == Qt.Key_T and event.modifiers() == Qt.NoModifier:
                self.activate_chat_input(prefix="")
                event.accept()
                return
            elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
                self.activate_chat_input(prefix="")
                event.accept()
                return
        elif event.key() == Qt.Key_Escape:
            self.deactivate_chat_input()
            event.accept()
            return

        # Проверка кастомного сочетания блокировки (Ctrl+L / Ctrl+K / Alt+L)
        configured_lock = self.config.get("hotkey_lock", "Ctrl+L")
        if (
            (configured_lock == "Ctrl+L" and event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_L)
            or (configured_lock == "Ctrl+K" and event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_K)
            or (configured_lock == "Alt+L" and event.modifiers() == Qt.AltModifier and event.key() == Qt.Key_L)
            or (configured_lock == "Ctrl+Shift+L" and (event.modifiers() == (Qt.ControlModifier | Qt.ShiftModifier)) and event.key() == Qt.Key_L)
        ):
            self.toggle_lock()
            event.accept()
            return

        # F3 локальное переключение
        if event.key() == Qt.Key_F3:
            self.toggle_overlay_visibility()
            event.accept()
            return

        # Навигация по истории команд стрелками Вверх/Вниз
        if self.input_field.hasFocus():
            if event.key() == Qt.Key_Up:
                if self.cmd_history and self.cmd_history_idx < len(self.cmd_history) - 1:
                    self.cmd_history_idx += 1
                    self.input_field.setText(self.cmd_history[len(self.cmd_history) - 1 - self.cmd_history_idx])
                event.accept()
                return
            elif event.key() == Qt.Key_Down:
                if self.cmd_history_idx > 0:
                    self.cmd_history_idx -= 1
                    self.input_field.setText(self.cmd_history[len(self.cmd_history) - 1 - self.cmd_history_idx])
                elif self.cmd_history_idx == 0:
                    self.cmd_history_idx = -1
                    self.input_field.clear()
                event.accept()
                return

        super().keyPressEvent(event)

    def send_chat_message(self):
        """Отправка набранного текста на сервер и возврат в режим клика насквозь."""
        text = self.input_field.text().strip()
        if not text:
            self.deactivate_chat_input()
            return

        # Сохранение в буфер истории
        if not self.cmd_history or self.cmd_history[-1] != text:
            self.cmd_history.append(text)
            if len(self.cmd_history) > 50:
                self.cmd_history.pop(0)
        self.cmd_history_idx = -1

        self.input_field.clear()
        self.worker.send_message(text)
        self.deactivate_chat_input()

    def open_settings(self):
        """Открытие модального окна настроек."""
        dlg = SettingsDialog(self, self.config)
        dlg.settings_saved.connect(self.on_settings_saved)
        dlg.exec_()

    def on_settings_saved(self, new_cfg: dict):
        """Применение сохраненных пользователем параметров."""
        self.config = new_cfg
        save_config(self.config)

        self.update_style_sheet()
        self.update_chat_font_style()
        self.title_label.setText(f"[{self.config.get('room', 'ROBLOX-RP-1')}]")

        # Применение режимов клика насквозь
        if self.config.get("click_through", False):
            self.set_click_through(True)
        else:
            self.set_click_through(False)

        # Обновление данных подключения и повторный вход в комнату
        self.worker.update_user_info(
            username=self.config["username"],
            room=self.config["room"],
            role=self.config["role"],
            color=self.config.get("user_color", "#5CABFF"),
        )

        # Безопасное обновление глобальной горячей клавиши без сброса чужих биндов
        self.init_global_hotkeys()

    # --- Обработчики сокет-сигналов из фонового потока ---
    def on_socket_connected(self):
        self.is_connected = True
        logger.info("Сокет-соединение с сервером успешно установлено.")
        if hasattr(self, "status_dot") and self.status_dot:
            self.status_dot.setStyleSheet("color: #22C55E; font-size: 14px;")
            self.status_dot.setToolTip("Подключено к серверу RP")

    def on_socket_disconnected(self):
        self.is_connected = False
        logger.warning("Соединение с сервером разорвано. Переподключение...")
        if hasattr(self, "status_dot") and self.status_dot:
            self.status_dot.setStyleSheet("color: #EF4444; font-size: 14px;")
            self.status_dot.setToolTip("Соединение разорвано. Переподключение...")

    def on_socket_error(self, err_msg: str):
        logger.error(f"Сетевая ошибка: {err_msg}")
        self.append_system_html(f"<span style='color: #EF4444;'><b>[Сетевая ошибка]:</b> {err_msg}</span>")

    def on_joined_room(self, data: dict):
        room = data.get("room", "")
        self.title_label.setText(f"[{room}]")
        history = data.get("history", [])
        self.chat_browser.clear()
        for msg in history:
            self.render_message_html(msg)

    def on_roster_updated(self, data: dict):
        members = data.get("members", [])
        self.room_members = members
        if hasattr(self, "roster_badge") and self.roster_badge:
            self.roster_badge.setText(f"{len(members)} Онлайн")

    def on_clear_chat(self):
        self.chat_browser.clear()
        self.append_system_html("<i>История чата была очищена.</i>")

    def on_message_received(self, msg: dict):
        self.render_message_html(msg)

        # Воспроизведение звука только для чужих входящих сообщений
        if self.config.get("sound_enabled", True):
            author = str(msg.get("author", "")).strip()
            my_username = str(self.config.get("username", "")).strip()
            mtype = msg.get("type", "chat")
            # Свои сообщения не озвучиваются, системные сообщения не озвучиваются
            if author and author != my_username and mtype != "system":
                play_notification_sound(self.config.get("sound_file", ""))

    # --- Рендеринг HTML сообщений (стилистика Roblox RP) ---
    def render_message_html(self, msg: dict):
        """Отображение сообщения с нужной цветовой маркировкой и безопасным экранированием HTML."""
        mtype = msg.get("type", "chat")
        author = html.escape(str(msg.get("author", "Неизвестный")))
        color = msg.get("color", "#5CABFF")
        raw_text = str(msg.get("text", ""))
        # Для системных подсказок со встроенными тегами оставляем как есть, остальной пользовательский текст экранируем
        text = raw_text if (mtype == "system" and ("<b>" in raw_text or "<code>" in raw_text)) else html.escape(raw_text)
        ts = html.escape(str(msg.get("timestamp", "")))
        role = html.escape(str(msg.get("role", "")))

        show_ts = self.config.get("show_timestamps", True)
        ts_html = f"<span style='color: #64748B; font-size: 11px;'>[{ts}]</span> " if (ts and show_ts) else ""
        role_tag = f"<span style='color: #94A3B8; font-size: 11px;'>[{role}]</span> " if role and role != "Гражданский" else ""

        col_me = self.config.get("color_me", "#d8b4fe")
        col_do = self.config.get("color_do", "#38bdf8")
        col_try_s = self.config.get("color_try_success", "#4ade80")
        col_try_f = self.config.get("color_try_fail", "#f87171")
        col_ooc = self.config.get("color_ooc", "#94a3b8")

        if mtype == "system":
            html_line = f"<div style='margin-bottom: 4px;'>{ts_html}<span style='color: #EAB308;'>{text}</span></div>"

        elif mtype == "me":
            # Форматирование /me: * Офицер Джон достает рацию *
            html_line = (
                f"<div style='margin-bottom: 4px; color: {col_me}; font-style: italic;'>"
                f"{ts_html}* <b style='color: {color};'>{author}</b> {text} *</div>"
            )

        elif mtype == "do":
            # Форматирование /do: * Замок багажника сорван (( Джон )) *
            html_line = (
                f"<div style='margin-bottom: 4px; color: {col_do};'>"
                f"{ts_html}* {text} <span style='color: #94A3B8;'>(( {author} ))</span> *</div>"
            )

        elif mtype == "try":
            # Форматирование /try: * Джон Взломал машину [Удачно] * или [Неудачно] (без 'пытается')
            success = msg.get("success", False)
            tag_color = col_try_s if success else col_try_f
            tag_text = msg.get("result_text") or ("Удачно" if success else "Неудачно")
            html_line = (
                f"<div style='margin-bottom: 4px; color: #CBD5E1;'>"
                f"{ts_html}* <b style='color: {color};'>{author}</b> {text} "
                f"<b style='color: {tag_color};'>[{tag_text}]</b> *</div>"
            )

        elif mtype == "ooc":
            # Форматирование /b: (( [OOC] Джон: Ребята, я АФК на 2 минуты ))
            html_line = (
                f"<div style='margin-bottom: 4px; color: {col_ooc};'>"
                f"{ts_html}(( [OOC] <b style='color: {color};'>{author}</b>: {text} ))</div>"
            )

        elif mtype == "shout":
            # Форматирование /s: [КРИК] Джон: ВСЕМ ОСТАВАТЬСЯ НА МЕСТАХ!
            html_line = (
                f"<div style='margin-bottom: 4px; color: #FB923C; font-weight: bold;'>"
                f"{ts_html}[КРИК] <span style='color: {color};'>{author}</span>: {text.upper()}!</div>"
            )

        elif mtype == "whisper":
            # Форматирование /c: [Тихо] Джон: тихо, охрана обходит коридор...
            html_line = (
                f"<div style='margin-bottom: 4px; color: #C084FC; font-style: italic;'>"
                f"{ts_html}[Тихо] <span style='color: {color};'>{author}</span>: {text}</div>"
            )

        else:
            # Обычная IC речь
            html_line = (
                f"<div style='margin-bottom: 4px; color: #F8FAFC;'>"
                f"{ts_html}{role_tag}<b style='color: {color};'>{author}</b>: {text}</div>"
            )

        self.chat_browser.append(html_line)
        # Автоматическая прокрутка вниз к самому свежему сообщению
        sb = self.chat_browser.verticalScrollBar()
        sb.setValue(sb.maximum())

    def append_system_html(self, text: str):
        self.chat_browser.append(f"<div style='margin-bottom: 4px; color: #EAB308;'>{text}</div>")
        sb = self.chat_browser.verticalScrollBar()
        sb.setValue(sb.maximum())

    def closeEvent(self, event):
        """Остановка сетевого потока и снятие горячих клавиш при закрытии программы."""
        if hasattr(self, "floating_btn") and self.floating_btn:
            self.floating_btn.close()
        if hasattr(self, "worker") and self.worker:
            self.worker.stop()
        if HAS_KEYBOARD_LIB:
            for h in self.registered_hooks:
                try:
                    keyboard.remove_hotkey(h)
                except Exception:
                    pass
            self.registered_hooks.clear()
        event.accept()


# ==============================================================================
# Точка входа в программу (Запуск приложения)
# ==============================================================================
def main():
    import signal
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    app = QApplication(sys.argv)
    app.setApplicationName("Roblox RP Чат-Оверлей")
    app.setStyle("Fusion")

    # Периодический таймер для перехвата сигналов ОС (SIGINT/Ctrl+C) в цикле событий Qt
    sig_timer = QtCore.QTimer()
    sig_timer.timeout.connect(lambda: None)
    sig_timer.start(500)

    # Базовая темная палитра Qt
    palette = QtGui.QPalette()
    palette.setColor(QtGui.QPalette.Window, QColor(25, 27, 31))
    palette.setColor(QtGui.QPalette.WindowText, Qt.white)
    palette.setColor(QtGui.QPalette.Base, QColor(18, 20, 24))
    palette.setColor(QtGui.QPalette.AlternateBase, QColor(25, 27, 31))
    palette.setColor(QtGui.QPalette.ToolTipBase, Qt.white)
    palette.setColor(QtGui.QPalette.ToolTipText, Qt.white)
    palette.setColor(QtGui.QPalette.Text, Qt.white)
    palette.setColor(QtGui.QPalette.Button, QColor(25, 27, 31))
    palette.setColor(QtGui.QPalette.ButtonText, Qt.white)
    palette.setColor(QtGui.QPalette.BrightText, Qt.red)
    palette.setColor(QtGui.QPalette.Highlight, QColor(59, 130, 246))
    palette.setColor(QtGui.QPalette.HighlightedText, Qt.white)
    app.setPalette(palette)

    overlay = RobloxChatOverlay()
    overlay.show()

    logger.info("=" * 65)
    logger.info("  Десктоп-оверлей Roblox RP успешно запущен")
    logger.info("  - Нажмите '/' или Enter для набора текста (поддерживается ENG/RU)")
    logger.info("  - Нажмите F3 для скрытия или показа оверлея")
    logger.info("  - Нажмите Ctrl+L для блокировки перетаскивания окна")
    logger.info("  - ВАЖНО: Запустите Roblox в режиме 'В окне' или 'Окно без рамок'")
    logger.info("=" * 65)

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
