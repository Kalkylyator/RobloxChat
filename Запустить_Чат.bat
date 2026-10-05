@echo off
chcp 65001 >nul
title Roblox RP Chat Overlay
color 0b

cd /d "%~dp0"

echo ========================================================
echo         Roblox RP Chat Overlay - Запуск Клиента
echo ========================================================
echo.

set PYCMD=
where python >nul 2>nul
if %errorlevel% equ 0 (
    set PYCMD=python
) else (
    where py >nul 2>nul
    if %errorlevel% equ 0 (
        set PYCMD=py
    )
)

if "%PYCMD%"=="" (
    color 0c
    echo [ОШИБКА] Python не найден на вашем компьютере!
    echo Скачайте Python: https://www.python.org/downloads/
    echo Обязательно отметьте "Add Python to PATH" при установке.
    echo.
    pause
    exit /b 1
)

echo [1/2] Проверка библиотек (PyQt5, socketio)...
%PYCMD% -m pip install -r requirements.txt --quiet

echo [2/2] Запуск чат-оверлея Roblox...
echo.
echo [Подсказка]: На экране появится подвижная кнопочка 💬.
echo Перетащите её в любое удобное место экрана. Нажмите на неё или / для ввода.
echo.
%PYCMD% client.py

if %errorlevel% neq 0 (
    color 0c
    echo.
    echo ========================================================
    echo [ОШИБКА] Сбой при работе клиента. Текст ошибки выше.
    echo ========================================================
    pause
)
