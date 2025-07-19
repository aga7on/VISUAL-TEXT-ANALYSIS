@echo off
echo ========================================
echo 🖼️ Визуальный анализ текста v3.0
echo ========================================
echo 🎬 Drag & Drop в DaVinci Resolve
echo 🤖 Менеджер системных промптов  
echo 💾 Постоянное сохранение изображений
echo ========================================

REM Проверяем наличие Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ОШИБКА: Python не найден!
    echo Пожалуйста, установите Python с https://python.org
    pause
    exit /b 1
)

echo ✅ Python найден

REM Создаем виртуальное окружение
echo 📦 Создание виртуального окружения...
if exist .venv (
    echo Виртуальное окружение уже существует
) else (
    python -m venv .venv
    if errorlevel 1 (
        echo ОШИБКА: Не удалось создать виртуальное окружение
        pause
        exit /b 1
    )
    echo ✅ Виртуальное окружение создано
)

REM Активируем виртуальное окружение
echo 🔧 Активация виртуального окружения...
call .venv\Scripts\activate.bat

REM Обновляем pip
echo 📥 Обновление pip...
python -m pip install --upgrade pip

REM Устанавливаем зависимости
echo 📦 Установка зависимостей...
pip install -r requirements.txt

if errorlevel 1 (
    echo ОШИБКА: Не удалось установить зависимости
    echo Попробуйте установить вручную:
    echo pip install streamlit requests aiohttp jinja2 duckduckgo-search Pillow beautifulsoup4 playwright
    pause
    exit /b 1
)

echo ✅ Зависимости установлены!

echo.
echo 📁 Создание необходимых папок...
if not exist "saved_images" mkdir saved_images
if not exist "used_in_davinci" mkdir used_in_davinci
if not exist "cache" mkdir cache
if not exist "templates" mkdir templates
echo ✅ Папки созданы

echo.
echo 📄 Создание файлов конфигурации...
if not exist "settings.json" (
    echo 📝 Создаем settings.json...
    (
        echo {
        echo   "llm_url": "http://localhost:1234/v1/chat/completions",
        echo   "llm_model": "local-llm",
        echo   "query_count": 1,
        echo   "image_count": 4,
        echo   "search_engine": "duckduckgo",
        echo   "search_language": "auto",
        echo   "url_parsing": false,
        echo   "system_prompt": "Создай короткий поисковый запрос (максимум 6 слов) для поиска изображений. Отвечай ТОЛЬКО ключевыми словами без объяснений."
        echo }
    ) > settings.json
    echo ✅ settings.json создан
) else (
    echo ✅ settings.json уже существует
)

if not exist "custom_prompts.json" (
    echo 📝 Создаем custom_prompts.json...
    echo {} > custom_prompts.json
    echo ✅ custom_prompts.json создан
) else (
    echo ✅ custom_prompts.json уже существует
)

REM Устанавливаем браузеры для Playwright (опционально)
echo.
echo 🌐 Установка браузеров для Playwright (опционально)...
echo ⚠️ Pinterest и некоторые поисковики отключены в текущей версии
echo ℹ️ Пропускаем установку браузеров...
REM playwright install firefox

echo.
echo 🧪 Тестирование установки...
python -c "import streamlit, requests, asyncio, jinja2, base64; print('✅ Все модули импортированы успешно')"
if errorlevel 1 (
    echo ❌ Ошибка импорта модулей
    pause
    exit /b 1
)

echo.
echo ========================================
echo ✅ УСТАНОВКА ЗАВЕРШЕНА УСПЕШНО!
echo ========================================
echo.
echo 🚀 Для запуска используйте: run.bat
echo 📖 Или вручную:
echo    1. call .venv\Scripts\activate.bat
echo    2. streamlit run app.py
echo.
echo 💡 Перед использованием:
echo    - Запустите LM Studio на http://localhost:1234
echo    - Загрузите любую модель в LM Studio
echo    - Откройте браузер на http://localhost:8501
echo.
echo 🆕 Новые функции v3.0:
echo    🎬 Drag & Drop изображений в DaVinci Resolve
echo    💾 Постоянное сохранение изображений в saved_images/
echo    🤖 Менеджер системных промптов с возможностью создания своих
echo    🔄 Кнопки перегенерации для каждого абзаца
echo    📊 Улучшенная статистика кэша и изображений
echo.
echo 📁 Структура папок:
echo    saved_images/     - Все найденные изображения (не удаляются)
echo    used_in_davinci/  - Копии изображений, перетащенных в DaVinci
echo    cache/            - Кэш поисковых запросов
echo    templates/        - HTML шаблоны для отчетов
echo.
echo 🔍 Доступные поисковики:
echo    ✅ DuckDuckGo (рекомендуется)
echo    ✅ Bing
echo    ✅ Yandex
echo    ✅ Pixabay
echo    ❌ Pinterest (отключен)
echo    ❌ Unsplash (отключен)
echo.
pause