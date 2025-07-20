# -*- coding: utf-8 -*-
"""
🖼️ Визуальный анализ текста
Приложение для автоматического поиска и добавления изображений к тексту с использованием ИИ
"""

import os
import json
import time
import base64
import streamlit as st
import requests
import asyncio
import shutil
from jinja2 import Environment, FileSystemLoader
from typing import List, Dict, Optional

# Импорт функций для работы с изображениями
try:
    import image_utils
    from image_utils import (download_images_async, extract_urls_from_text, 
                           search_images_from_urls)
    # Импортируем search_images отдельно для проверки
    search_images = image_utils.search_images
except ImportError as e:
    st.error(f"Ошибка импорта image_utils: {e}")
    st.error("Проверьте, что все зависимости установлены: pip install -r requirements.txt")
    st.stop()
except AttributeError as e:
    st.error(f"Ошибка атрибута в image_utils: {e}")
    st.error("Проверьте целостность файла image_utils.py")
    st.stop()

# === НАСТРОЙКИ ===
SETTINGS_FILE = "settings.json"
CUSTOM_PROMPTS_FILE = "custom_prompts.json"
HISTORY_FILE = "history.json"
TEMPLATE_DIR = "templates"
HTML_OUT = "output.html"
IMAGES_DIR = "saved_images"
USED_IMAGES_DIR = "used_in_davinci"

# Создаем необходимые папки
os.makedirs(IMAGES_DIR, exist_ok=True)
os.makedirs(USED_IMAGES_DIR, exist_ok=True)
os.makedirs(TEMPLATE_DIR, exist_ok=True)

# === НАСТРОЙКИ ПО УМОЛЧАНИЮ ===
DEFAULT_SETTINGS = {
    "llm_url": "http://localhost:1234/v1/chat/completions",
    "llm_model": "local-llm",
    "llm_api_key": "",
    "image_count": 4,
    "search_engine": "duckduckgo",
    "search_language": "auto",
    "url_parsing": True,
    "system_prompt": "Создай короткие поисковые запросы (максимум 3 слова каждый) для поиска изображений к тексту. Каждый запрос на новой строке. Отвечай ТОЛЬКО ключевыми словами без объяснений.",
    "split_long_paragraphs": False,
    "smart_queries": True,
    "searxng_url": "http://localhost:8080",
    "searxng_count": 6,
    "duckduckgo_count": 3,
    "pixabay_count": 3,
    "pinterest_count": 3,
    "tenor_count": 3
}

DEFAULT_PROMPTS = {
    "ЗАПРОСОВ ДЛЯ ИЗОБРАЖЕНИЙ": "🔍 ТЫ — ЭКСПЕРТ ПО СОЗДАНИЮ ПОИСКОВЫХ ЗАПРОСОВ ДЛЯ ИЗОБРАЖЕНИЙ\n\n🎯 ЗАДАЧА:\nПрочитай текст. Найди в нём отдельные темы и создай по одной поисковый запрос для каждой.\nТвоя цель — визуализировать каждую тему: подумай, что именно должно быть на изображении, и преврати это в чёткий, короткий запрос.\n\n🧠 КАК ДУМАТЬ О КАЖДОЙ ТЕМЕ:\nПеред тем как создать запрос, проанализируй тему с помощью этих вопросов:\n    Что именно происходит?\n    Кто или что участвует?\n    Где и в каком контексте?\n\n✅ ПРАВИЛА СОЗДАНИЯ ЗАПРОСОВ:\n- Максимум 5 слов в одном запросе\n- Каждый запрос на отдельной строке\n- Конкретные объекты, а не абстракции\n- Визуально представимые понятия\n- БЕЗ нумерации, БЕЗ кавычек, БЕЗ объяснений\n\n🎯 ЦЕЛЬ: Создать 3-8 запросов, каждый из которых поможет найти изображение, иллюстрирующее конкретную тему из текста.",
    "Простая система": "Создай короткие поисковые запросы для изображений к тексту. Каждый запрос максимум 3 слова, каждый на новой строке."
}

# === ФУНКЦИИ РАБОТЫ С НАСТРОЙКАМИ ===
def load_settings() -> Dict:
    """Загрузка настроек из файла"""
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                settings = json.load(f)
                # Добавляем отсутствующие настройки
                for key, value in DEFAULT_SETTINGS.items():
                    if key not in settings:
                        settings[key] = value
                return settings
    except Exception as e:
        st.error(f"Ошибка загрузки настроек: {e}")
    
    return DEFAULT_SETTINGS.copy()

def save_settings(settings: Dict) -> None:
    """Сохранение настроек в файл"""
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except Exception as e:
        st.error(f"Ошибка сохранения настроек: {e}")

def load_custom_prompts() -> Dict:
    """Загрузка пользовательских промптов"""
    try:
        if os.path.exists(CUSTOM_PROMPTS_FILE):
            with open(CUSTOM_PROMPTS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        st.error(f"Ошибка загрузки промптов: {e}")
    
    return DEFAULT_PROMPTS.copy()

def save_custom_prompts(prompts: Dict) -> None:
    """Сохранение пользовательских промптов"""
    try:
        with open(CUSTOM_PROMPTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(prompts, f, ensure_ascii=False, indent=2)
    except Exception as e:
        st.error(f"Ошибка сохранения промптов: {e}")

# === ФУНКЦИИ РАБОТЫ С ИСТОРИЕЙ ===
def load_history() -> List[Dict]:
    """Загрузка истории обработки"""
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        st.error(f"Ошибка загрузки истории: {e}")
    
    return []

def save_to_history(text: str, paragraphs_count: int, images_count: int, search_engine: str, language: str) -> None:
    """Сохранение записи в историю"""
    try:
        history = load_history()
        
        # Создаем новую запись
        entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "text_preview": text[:100] + "..." if len(text) > 100 else text,
            "paragraphs_count": paragraphs_count,
            "images_count": images_count,
            "search_engine": search_engine,
            "language": language
        }
        
        # Добавляем в начало списка
        history.insert(0, entry)
        
        # Ограничиваем историю 50 записями
        history = history[:50]
        
        # Сохраняем
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
            
    except Exception as e:
        st.error(f"Ошибка сохранения в историю: {e}")

# === ФУНКЦИИ РАБОТЫ С LLM ===
def get_available_models(llm_url: str, api_key: str = None) -> List[str]:
    """Получение списка доступных моделей через API"""
    try:
        # Специальная обработка для Gemini API
        if ('generativelanguage.googleapis.com' in llm_url or 
            'googleapis.com' in llm_url or 
            'gemini' in llm_url.lower()):
            return get_gemini_models(api_key)
        
        # Проверяем и исправляем URL
        if not llm_url.endswith('/v1/models'):
            base_url = llm_url.replace('/v1/chat/completions', '').rstrip('/')
            models_url = f"{base_url}/v1/models"
        else:
            models_url = llm_url
        
        headers = {'Content-Type': 'application/json'}
        if api_key:
            headers['Authorization'] = f'Bearer {api_key}'
        
        print(f"🔍 Проверяем доступные модели: {models_url}")
        
        response = requests.get(models_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            models = []
            
            # Обрабатываем разные форматы ответов API
            if 'data' in data and isinstance(data['data'], list):
                # OpenAI-совместимый формат
                for model in data['data']:
                    if isinstance(model, dict) and 'id' in model:
                        models.append(model['id'])
                    elif isinstance(model, str):
                        models.append(model)
            elif 'models' in data:
                # Альтернативный формат
                models = data['models']
            elif isinstance(data, list):
                # Простой список
                models = data
            
            # Фильтруем и сортируем модели
            filtered_models = []
            for model in models:
                if isinstance(model, str) and model.strip():
                    filtered_models.append(model.strip())
            
            filtered_models.sort()
            print(f"✅ Найдено {len(filtered_models)} моделей")
            return filtered_models
            
        else:
            print(f"❌ Ошибка API: {response.status_code}")
            return []
            
    except requests.exceptions.Timeout:
        print("⏰ Таймаут при получении моделей")
        return []
    except requests.exceptions.ConnectionError:
        print("🔌 Ошибка соединения с API")
        return []
    except Exception as e:
        print(f"❌ Ошибка получения моделей: {e}")
        return []

def get_gemini_models(api_key: str = None) -> List[str]:
    """Получение списка моделей Gemini API"""
    try:
        if not api_key:
            print("❌ API ключ обязателен для Gemini API")
            return []
        
        # URL для получения списка моделей Gemini
        models_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        
        print(f"🔍 Проверяем модели Gemini API...")
        
        response = requests.get(models_url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            models = []
            
            # Обрабатываем ответ Gemini API
            if 'models' in data:
                for model in data['models']:
                    if isinstance(model, dict) and 'name' in model:
                        # Извлекаем имя модели из полного пути
                        model_name = model['name']
                        if model_name.startswith('models/'):
                            model_name = model_name.replace('models/', '')
                        
                        # Фильтруем только модели для генерации текста
                        supported_methods = model.get('supportedGenerationMethods', [])
                        if 'generateContent' in supported_methods:
                            models.append(model_name)
            
            models.sort()
            print(f"✅ Найдено {len(models)} моделей Gemini")
            return models
            
        elif response.status_code == 400:
            print("❌ Неверный API ключ для Gemini")
            return []
        elif response.status_code == 403:
            print("❌ Доступ запрещен - проверьте API ключ Gemini")
            return []
        else:
            print(f"❌ Ошибка Gemini API: {response.status_code}")
            return []
            
    except requests.exceptions.Timeout:
        print("⏰ Таймаут при получении моделей Gemini")
        return []
    except requests.exceptions.ConnectionError:
        print("🔌 Ошибка соединения с Gemini API")
        return []
    except Exception as e:
        print(f"❌ Ошибка получения моделей Gemini: {e}")
        return []

def ask_gemini(prompt: str, system: str, model: str, api_key: str = None) -> str:
    """Запрос к Gemini API"""
    try:
        if not api_key:
            print("❌ API ключ обязателен для Gemini API")
            return ""
        
        # URL для генерации контента Gemini
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        
        # Формируем запрос в формате Gemini API
        # Объединяем системный промпт и пользовательский запрос
        # Делаем промпт более безопасным для фильтров Gemini
        safe_prompt = f"""Задача: {system}

Текст для обработки: {prompt}

Пожалуйста, выполни задачу и предоставь результат в виде списка ключевых слов, каждое на новой строке:"""
        
        data = {
            "contents": [{
                "parts": [{
                    "text": safe_prompt
                }]
            }],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 200,
                "topP": 0.8,
                "topK": 10
            }
        }
        
        headers = {'Content-Type': 'application/json'}
        
        response = requests.post(url, json=data, headers=headers, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            
            # Отладочная информация
            print(f"🔍 Структура ответа Gemini: {list(result.keys())}")
            if 'usageMetadata' in result:
                usage = result['usageMetadata']
                print(f"📊 Использование токенов: {usage}")
            
            # Извлекаем ответ из структуры Gemini
            if 'candidates' in result and len(result['candidates']) > 0:
                candidate = result['candidates'][0]
                print(f"🔍 Структура candidate: {list(candidate.keys())}")
                
                # Проверяем причину блокировки
                if 'finishReason' in candidate:
                    finish_reason = candidate['finishReason']
                    if finish_reason == 'SAFETY':
                        print("⚠️ Ответ заблокирован фильтрами безопасности Gemini")
                        return ""
                    elif finish_reason == 'RECITATION':
                        print("⚠️ Ответ заблокирован из-за возможного плагиата")
                        return ""
                    elif finish_reason == 'MAX_TOKENS':
                        print("⚠️ Достигнут лимит токенов - ответ может быть обрезан")
                        # Продолжаем обработку, так как частичный ответ может быть полезен
                    elif finish_reason not in ['STOP']:
                        print(f"⚠️ Неожиданная причина завершения: {finish_reason}")
                
                if 'content' in candidate:
                    content = candidate['content']
                    print(f"🔍 Структура content: {list(content.keys()) if isinstance(content, dict) else type(content)}")
                    
                    # Стандартная структура с parts
                    if isinstance(content, dict) and 'parts' in content and isinstance(content['parts'], list):
                        parts = content['parts']
                        if len(parts) > 0 and isinstance(parts[0], dict) and 'text' in parts[0]:
                            response_text = parts[0]['text'].strip()
                            print(f"✅ Получен ответ Gemini (parts): {response_text[:100]}...")
                            return response_text
                    
                    # Прямой текст в content
                    elif isinstance(content, dict) and 'text' in content:
                        response_text = content['text'].strip()
                        print(f"✅ Получен ответ Gemini (content.text): {response_text[:100]}...")
                        return response_text
                    
                    # Content как строка
                    elif isinstance(content, str) and content.strip():
                        print(f"✅ Получен ответ Gemini (строка): {content[:100]}...")
                        return content.strip()
                    
                    # Новая структура Gemini 2.5 - проверяем все поля рекурсивно
                    elif isinstance(content, dict):
                        print(f"🔍 Полная структура content: {content}")
                        
                        def extract_text_recursive(obj, path=""):
                            """Рекурсивно ищем текст в структуре"""
                            if isinstance(obj, str) and len(obj.strip()) > 10:
                                return obj.strip()
                            elif isinstance(obj, dict):
                                for key, value in obj.items():
                                    if key == 'text' and isinstance(value, str) and value.strip():
                                        return value.strip()
                                    result = extract_text_recursive(value, f"{path}.{key}")
                                    if result:
                                        return result
                            elif isinstance(obj, list):
                                for i, item in enumerate(obj):
                                    result = extract_text_recursive(item, f"{path}[{i}]")
                                    if result:
                                        return result
                            return None
                        
                        extracted_text = extract_text_recursive(content)
                        if extracted_text:
                            print(f"✅ Найден текст в структуре: {extracted_text[:100]}...")
                            return extracted_text
                else:
                    print("⚠️ Candidate не содержит content - возможно заблокирован")
            else:
                print("⚠️ Нет candidates в ответе - возможно все ответы заблокированы")
            
            # Проверяем альтернативные структуры в корне ответа
            if 'text' in result:
                response_text = result['text'].strip()
                print(f"✅ Получен ответ Gemini (прямой text): {response_text[:100]}...")
                return response_text
            
            # Последняя попытка - ищем любой текст в структуре
            def find_any_text(obj, path="root"):
                """Ищем любой осмысленный текст в структуре ответа"""
                if isinstance(obj, str) and len(obj.strip()) > 10:
                    # Проверяем, что это не служебная информация
                    if not any(keyword in obj.lower() for keyword in ['model', 'version', 'id', 'metadata', 'usage']):
                        return obj.strip()
                elif isinstance(obj, dict):
                    for key, value in obj.items():
                        if key in ['text', 'content', 'message', 'response']:
                            result = find_any_text(value, f"{path}.{key}")
                            if result:
                                return result
                    # Если не нашли в приоритетных полях, ищем везде
                    for key, value in obj.items():
                        if key not in ['usageMetadata', 'modelVersion', 'responseId', 'finishReason', 'index']:
                            result = find_any_text(value, f"{path}.{key}")
                            if result:
                                return result
                elif isinstance(obj, list):
                    for i, item in enumerate(obj):
                        result = find_any_text(item, f"{path}[{i}]")
                        if result:
                            return result
                return None
            
            fallback_text = find_any_text(result)
            if fallback_text:
                print(f"✅ Найден текст в структуре ответа: {fallback_text[:100]}...")
                return fallback_text
            
            print(f"❌ Не удалось извлечь текст из ответа Gemini")
            print(f"🔍 Полная структура для отладки: {result}")
            return ""
            
        elif response.status_code == 400:
            print("❌ Неверный запрос к Gemini API")
            return ""
        elif response.status_code == 403:
            print("❌ Доступ запрещен - проверьте API ключ Gemini")
            return ""
        elif response.status_code == 429:
            print("❌ Превышен лимит запросов Gemini API")
            return ""
        else:
            print(f"❌ Ошибка Gemini API: {response.status_code}")
            return ""
        
    except requests.exceptions.Timeout:
        print("⏰ Таймаут запроса к Gemini API")
        return ""
    except requests.exceptions.ConnectionError:
        print("🔌 Ошибка соединения с Gemini API")
        return ""
    except Exception as e:
        print(f"❌ Ошибка запроса к Gemini: {e}")
        return ""

def ask_llm(prompt: str, system: str, llm_url: str, model: str, api_key: str = None) -> str:
    """Запрос к LLM серверу"""
    try:
        # Специальная обработка для Gemini API
        if ('generativelanguage.googleapis.com' in llm_url or 
            'googleapis.com' in llm_url or 
            'gemini' in llm_url.lower()):
            return ask_gemini(prompt, system, model, api_key)
        
        # Проверяем и исправляем URL
        if not llm_url.endswith('/v1/chat/completions'):
            llm_url = llm_url.rstrip('/') + '/v1/chat/completions'
        
        # Проверяем доступность сервера
        base_url = llm_url.replace('/v1/chat/completions', '')
        headers = {'Content-Type': 'application/json'}
        if api_key:
            headers['Authorization'] = f'Bearer {api_key}'
        
        try:
            health_response = requests.get(f"{base_url}/health", headers=headers, timeout=5)
        except:
            try:
                health_response = requests.get(f"{base_url}/v1/models", headers=headers, timeout=5)
            except:
                pass
        
        # Формируем запрос
        data = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 200
        }
        
        response = requests.post(llm_url, json=data, headers=headers, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            if 'choices' in result and len(result['choices']) > 0:
                return result['choices'][0]['message']['content'].strip()
        
        return ""
        
    except Exception as e:
        st.error(f"Ошибка запроса к LLM: {e}")
        return ""

def generate_smart_queries(paragraph: str, settings: Dict) -> List[str]:
    """Генерация умных поисковых запросов через LLM"""
    try:
        system_prompt = settings.get("system_prompt", DEFAULT_SETTINGS["system_prompt"])
        
        user_prompt = f"Текст для анализа:\n{paragraph}\n\nСоздай короткие поисковые запросы для изображений к этому тексту."
        
        response = ask_llm(
            prompt=user_prompt,
            system=system_prompt,
            llm_url=settings["llm_url"],
            model=settings["llm_model"],
            api_key=settings.get("llm_api_key")
        )
        
        if not response:
            return []
        
        # Отладочная информация (можно отключить в продакшене)
        if settings.get("debug_mode", False):
            st.write(f"🔍 **Сырой ответ LLM:** `{response}`")
        
        # Обрабатываем ответ от LLM с тегами <think>
        cleaned_response = clean_llm_response(response)
        
        if settings.get("debug_mode", False):
            st.write(f"🧹 **Очищенный ответ:** `{cleaned_response}`")
            st.write(f"📏 **Длина очищенного ответа:** {len(cleaned_response)}")
            if not cleaned_response:
                st.error("⚠️ Очищенный ответ пустой!")
        
        if not cleaned_response:
            return []
        
        # Парсим ответ
        queries = []
        
        # Пробуем разные способы разделения
        if '|' in cleaned_response:
            queries = [q.strip() for q in cleaned_response.split('|')]
        else:
            queries = [q.strip() for q in cleaned_response.split('\n')]
        
        # Очищаем и фильтруем запросы
        clean_queries = []
        for query in queries:
            query = query.strip()
            # Убираем нумерацию и лишние символы
            query = query.lstrip('0123456789.- ')
            query = query.strip('"\'`')
            
            if query and len(query) > 2 and not query.startswith('<'):
                clean_queries.append(query)
        
        # Отладочная информация для запросов
        if settings.get("debug_mode", False):
            st.write(f"🎯 **Найдено запросов:** {len(clean_queries)}")
            
            # Безопасное получение общего количества изображений
            total_images = settings.get("image_count", 4)
            if isinstance(total_images, dict):
                # Для множественного режима суммируем все значения
                total_images = sum(v for k, v in total_images.items() if k.endswith('_count'))
                st.write(f"📊 **Настройка изображений:** {settings['image_count']} (всего: {total_images})")
            else:
                st.write(f"📊 **Настройка изображений:** {total_images} общих")
            
            if len(clean_queries) > 0 and isinstance(total_images, int):
                per_query = total_images // len(clean_queries)
                remainder = total_images % len(clean_queries)
                st.write(f"📈 **Распределение:** {per_query} на запрос + {remainder} остаток")
            
            for i, q in enumerate(clean_queries, 1):
                st.write(f"   {i}. `{q}`")
        
        # Возвращаем ВСЕ найденные запросы без ограничений
        return clean_queries
        
    except Exception as e:
        st.error(f"Ошибка генерации запросов: {e}")
        return []

def clean_llm_response(response: str) -> str:
    """
    Очищает ответ LLM от служебных тегов и извлекает финальный ответ
    """
    try:
        import re
        
        # Обрабатываем случай с незакрытым тегом think
        if 'think' in response.lower():
            # Ищем паттерны think (с тегами или без)
            if '<think>' in response and '</think>' in response:
                # Стандартный случай с закрытыми тегами
                response = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL)
            elif 'think' in response.lower():
                # Случай с незакрытым think или /think
                # Ищем все после последнего упоминания think или /think
                think_patterns = ['/think', 'think']
                last_think_pos = -1
                
                for pattern in think_patterns:
                    pos = response.lower().rfind(pattern)
                    if pos > last_think_pos:
                        last_think_pos = pos
                
                if last_think_pos != -1:
                    # Берем текст после последнего think/think
                    after_think = response[last_think_pos:]
                    # Убираем сам паттерн think
                    after_think = re.sub(r'^[/]?think\s*', '', after_think, flags=re.IGNORECASE)
                    response = after_think.strip()
        
        # Удаляем любые оставшиеся XML-подобные теги
        response = re.sub(r'<[^>]+>', '', response)
        
        # Удаляем лишние пробелы в начале и конце
        response = response.strip()
        
        # Если ответ слишком длинный (больше 500 символов), скорее всего это объяснение
        if len(response) > 500:
            # Ищем короткие строки в конце - они скорее всего запросы
            lines = response.split('\n')
            short_lines = []
            
            # Берем строки из конца, которые короче 50 символов
            for line in reversed(lines):
                line = line.strip()
                if line and len(line) < 50 and len(line) > 5:
                    short_lines.insert(0, line)
                    if len(short_lines) >= 6:  # Максимум 6 запросов
                        break
            
            if short_lines:
                response = '\n'.join(short_lines)
        
        # Разбиваем на строки и очищаем каждую
        lines = response.split('\n')
        clean_lines = []
        
        for line in lines:
            line = line.strip()
            
            # Пропускаем пустые строки
            if not line:
                continue
                
            # Пропускаем длинные объяснения (больше 50 символов)
            if len(line) > 50:
                continue
                
            # Пропускаем строки с объяснениями
            if line.startswith(('Вот', 'Для', 'Я создал', 'Создал', 'Анализ', 'Текст', 'Поисковые запросы', 'Запросы', 'Хм,', 'Пользователь')):
                continue
                
            # Убираем нумерацию и маркеры
            line = re.sub(r'^[\d\.\-\•\*\s]+', '', line).strip()
            
            # Убираем кавычки и лишние символы
            line = line.strip('"\'`')
            
            # Проверяем, что строка не пустая, достаточно длинная, но не слишком длинная
            if line and 5 <= len(line) <= 50 and not line.startswith('<'):
                clean_lines.append(line)
        
        # Возвращаем очищенные строки
        if clean_lines:
            return '\n'.join(clean_lines)
        
        # Если ничего не найдено, возвращаем исходный ответ без тегов
        return response
        
    except Exception as e:
        print(f"Ошибка очистки ответа LLM: {e}")
        return response

# === ФУНКЦИИ ОБРАБОТКИ ТЕКСТА ===
def split_text_into_paragraphs(text: str, split_long: bool = False) -> List[str]:
    """Разделение текста на абзацы"""
    # Разделяем по двойным переносам строк
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    
    if not paragraphs:
        # Если нет двойных переносов, разделяем по одинарным
        paragraphs = [p.strip() for p in text.split('\n') if p.strip()]
    
    if split_long:
        # Разделяем длинные абзацы (более 500 символов)
        split_paragraphs = []
        for p in paragraphs:
            if len(p) > 500:
                # Разделяем по предложениям
                sentences = p.split('. ')
                current_chunk = ""
                
                for sentence in sentences:
                    if len(current_chunk + sentence) < 500:
                        current_chunk += sentence + ". "
                    else:
                        if current_chunk:
                            split_paragraphs.append(current_chunk.strip())
                        current_chunk = sentence + ". "
                
                if current_chunk:
                    split_paragraphs.append(current_chunk.strip())
            else:
                split_paragraphs.append(p)
        
        paragraphs = split_paragraphs
    
    return paragraphs

def process_paragraph(paragraph: str, settings: Dict) -> Dict:
    """Обработка одного абзаца"""
    result = {
        "text": paragraph,
        "queries": [],
        "images": [],
        "url_images": []
    }
    
    try:
        # Генерируем поисковые запросы
        if settings["smart_queries"]:
            # Убираем ограничение query_count - используем все запросы от LLM
            queries = generate_smart_queries(paragraph, settings)
        else:
            # Простая генерация запросов (первые слова абзаца)
            words = paragraph.split()[:3]
            queries = [" ".join(words)] if words else []
        
        result["queries"] = queries
        
        # Поиск изображений по запросам
        all_images = []
        
        # Определяем количество изображений на запрос
        if len(queries) > 0:
            # Безопасное получение общего количества изображений
            total_images = settings.get("image_count", 4)
            if isinstance(total_images, dict):
                # Для множественного режима используем индивидуальные настройки
                images_per_query = 1  # Минимум 1 изображение на запрос
                remainder = 0
            else:
                # Распределяем общее количество изображений между запросами
                images_per_query = max(1, total_images // len(queries))
                # Если остается остаток, добавляем к первым запросам
                remainder = total_images % len(queries)
        else:
            images_per_query = 1
            remainder = 0
        
        for i, query in enumerate(queries):
            if query:
                # Определяем количество изображений для этого запроса
                current_count = images_per_query
                if i < remainder:  # Добавляем остаток к первым запросам
                    current_count += 1
                
                if settings.get("debug_mode", False):
                    st.write(f"🔍 **Запрос {i+1}:** `{query}` (ищем {current_count} изображений)")
                
                # Определяем тип поиска
                if isinstance(settings["search_engine"], list):
                    # Множественный режим - используем индивидуальные настройки
                    engine_images = {}
                    for engine in settings["search_engine"]:
                        engine_count = settings.get(f"{engine}_count", 3)
                        # В множественном режиме используем настройки для каждого поисковика
                        engine_images[engine] = engine_count
                    
                    # Поиск с индивидуальными настройками
                    for engine in settings["search_engine"]:
                        engine_count = engine_images.get(engine, 1)
                        
                        if settings.get("debug_mode", False):
                            st.write(f"   🔍 {engine}: ищем {engine_count} изображений")
                        
                        images = search_images(
                            query=query,
                            max_results=engine_count,
                            search_engine=engine,
                            searxng_url=settings.get("searxng_url", "http://localhost:8080")
                        )
                        
                        # Добавляем метаданные
                        for img in images:
                            img["query"] = query
                            img["search_engine"] = engine
                        
                        all_images.extend(images)
                else:
                    # Одиночный режим
                    images = search_images(
                        query=query,
                        max_results=current_count,
                        search_engine=settings["search_engine"],
                        searxng_url=settings.get("searxng_url", "http://localhost:8080")
                    )
                    
                    # Добавляем метаданные
                    for img in images:
                        img["query"] = query
                        img["search_engine"] = settings["search_engine"]
                    
                    all_images.extend(images)
        
        result["images"] = all_images
        
        # Поиск изображений по URL (если включено)
        if settings["url_parsing"]:
            url_images = search_images_from_urls(paragraph, max_images_per_url=2)
            result["url_images"] = url_images
        
    except Exception as e:
        st.error(f"Ошибка обработки абзаца: {e}")
    
    return result

# === ФУНКЦИИ СОЗДАНИЯ ОТЧЕТОВ ===
def create_html_report(results: List[Dict], settings: Dict) -> str:
    """Создание HTML отчета"""
    try:
        # Создаем базовый шаблон если его нет
        template_path = os.path.join(TEMPLATE_DIR, "report.html")
        if not os.path.exists(template_path):
            create_default_template()
        
        # Загружаем шаблон
        env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
        template = env.get_template("report.html")
        
        # Подготавливаем данные
        total_images = sum(len(r["images"]) + len(r["url_images"]) for r in results)
        
        # Рендерим HTML
        html_content = template.render(
            results=results,
            settings=settings,
            total_paragraphs=len(results),
            total_images=total_images,
            generation_time=time.strftime("%Y-%m-%d %H:%M:%S")
        )
        
        # Сохраняем файл
        with open(HTML_OUT, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return HTML_OUT
        
    except Exception as e:
        st.error(f"Ошибка создания HTML отчета: {e}")
        return ""

def create_default_template():
    """Создание базового HTML шаблона"""
    template_content = """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Визуальный анализ текста</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }
        .header { background: #f4f4f4; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
        .paragraph { margin-bottom: 30px; border: 1px solid #ddd; padding: 15px; border-radius: 8px; }
        .text { background: #f9f9f9; padding: 10px; border-radius: 4px; margin-bottom: 15px; }
        .queries { margin-bottom: 15px; }
        .query-tag { background: #007bff; color: white; padding: 4px 8px; border-radius: 4px; margin: 2px; display: inline-block; font-size: 12px; }
        .images { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 15px; }
        .image-item { border: 1px solid #ddd; border-radius: 8px; overflow: hidden; }
        .image-item img { width: 100%; height: 150px; object-fit: cover; }
        .image-meta { padding: 10px; font-size: 12px; background: #f8f9fa; }
        .stats { background: #e9ecef; padding: 15px; border-radius: 8px; margin-bottom: 20px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🖼️ Визуальный анализ текста</h1>
        <div class="stats">
            <strong>Статистика:</strong> 
            {{ total_paragraphs }} абзацев, {{ total_images }} изображений | 
            Поисковик: {{ settings.search_engine }} | 
            Сгенерировано: {{ generation_time }}
        </div>
    </div>

    {% for result in results %}
    <div class="paragraph">
        <div class="text">{{ result.text }}</div>
        
        {% if result.queries %}
        <div class="queries">
            <strong>🔍 Поисковые запросы:</strong>
            {% for query in result.queries %}
            <span class="query-tag">{{ query }}</span>
            {% endfor %}
        </div>
        {% endif %}
        
        {% if result.images %}
        <div class="images">
            {% for image in result.images %}
            <div class="image-item">
                <img src="{{ image.url }}" alt="{{ image.title }}" loading="lazy">
                <div class="image-meta">
                    <strong>Запрос:</strong> {{ image.query }}<br>
                    <strong>Источник:</strong> {{ image.search_engine }}<br>
                    {% if image.title %}<strong>Название:</strong> {{ image.title }}{% endif %}
                </div>
            </div>
            {% endfor %}
        </div>
        {% endif %}
    </div>
    {% endfor %}
</body>
</html>"""
    
    template_path = os.path.join(TEMPLATE_DIR, "report.html")
    with open(template_path, 'w', encoding='utf-8') as f:
        f.write(template_content)

# === ОСНОВНОЕ ПРИЛОЖЕНИЕ ===
def main():
    """Основная функция приложения"""
    st.set_page_config(
        page_title="🖼️ Визуальный анализ текста",
        page_icon="🖼️",
        layout="wide"
    )
    
    st.title("🖼️ Визуальный анализ текста")
    st.markdown("*Автоматический поиск и добавление изображений к тексту с использованием ИИ*")
    
    # Загружаем настройки
    if 'settings' not in st.session_state:
        st.session_state.settings = load_settings()
    
    # Боковая панель с настройками
    with st.sidebar:
        st.header("⚙️ Настройки")
        
        # Настройки LLM
        st.subheader("🤖 LLM Сервер")
        llm_url = st.text_input(
            "URL сервера",
            value=st.session_state.settings["llm_url"],
            help="Например: http://localhost:1234, https://api.openai.com или https://generativelanguage.googleapis.com для Gemini"
        )
        
        llm_api_key = st.text_input(
            "API ключ (опционально)",
            value=st.session_state.settings.get("llm_api_key", ""),
            type="password",
            help="Для внешних API (OpenAI, Anthropic, Google Gemini и др.). Оставьте пустым для локальных серверов"
        )
        
        # Модель с автоматическим получением списка
        col_model, col_refresh = st.columns([4, 1])
        
        with col_model:
            # Инициализируем список доступных моделей в session_state
            if 'available_models' not in st.session_state:
                st.session_state.available_models = []
            
            # Если есть доступные модели, показываем selectbox, иначе text_input
            if st.session_state.available_models:
                current_model = st.session_state.settings.get("llm_model", "local-llm")
                if current_model not in st.session_state.available_models:
                    st.session_state.available_models.insert(0, current_model)
                
                try:
                    default_index = st.session_state.available_models.index(current_model)
                except ValueError:
                    default_index = 0
                
                llm_model = st.selectbox(
                    "Модель",
                    options=st.session_state.available_models,
                    index=default_index,
                    help="Выберите модель из списка доступных"
                )
            else:
                llm_model = st.text_input(
                    "Модель",
                    value=st.session_state.settings.get("llm_model", "local-llm"),
                    help="Название модели LLM (нажмите 🔄 для автоматического получения списка)"
                )
        
        with col_refresh:
            st.write("")  # Отступ для выравнивания
            if st.button("🔄", help="Обновить список доступных моделей"):
                with st.spinner("Получаем список моделей..."):
                    models = get_available_models(llm_url, llm_api_key if llm_api_key else None)
                    
                    if models:
                        st.session_state.available_models = models
                        st.success(f"✅ Найдено {len(models)} моделей!")
                        st.rerun()
                    else:
                        st.error("❌ Не удалось получить список моделей")
                        st.info("💡 Проверьте URL сервера и API ключ")
        
        # Менеджер промптов
        st.subheader("🧠 Промпты для LLM")
        prompts = load_custom_prompts()
        
        selected_prompt = st.selectbox(
            "Выберите промпт",
            options=list(prompts.keys()),
            help="Выберите готовый промпт или создайте свой"
        )
        
        # Показываем выбранный промпт
        current_prompt = prompts.get(selected_prompt, DEFAULT_SETTINGS["system_prompt"])
        
        # Управление промптами
        col1, col2 = st.columns([3, 1])
        with col1:
            # Возможность редактирования
            if st.checkbox("Редактировать промпт"):
                edited_prompt = st.text_area(
                    "Системный промпт",
                    value=current_prompt,
                    height=150,
                    help="Промпт для генерации поисковых запросов"
                )
                
                if st.button("💾 Сохранить промпт"):
                    prompts[selected_prompt] = edited_prompt
                    save_custom_prompts(prompts)
                    st.success("Промпт сохранен!")
                    st.rerun()
            else:
                edited_prompt = current_prompt
        
        with col2:
            # Инициализируем состояния для управления промптами
            if 'show_new_prompt' not in st.session_state:
                st.session_state.show_new_prompt = False
            if 'show_delete_confirm' not in st.session_state:
                st.session_state.show_delete_confirm = False
            
            # Добавление нового промпта
            if st.button("➕ Новый"):
                st.session_state.show_new_prompt = not st.session_state.show_new_prompt
                st.session_state.show_delete_confirm = False
            
            if st.session_state.show_new_prompt:
                new_name = st.text_input("Название промпта:", key="new_prompt_name")
                col_create, col_cancel = st.columns(2)
                
                with col_create:
                    if st.button("✅ Создать", key="create_prompt"):
                        if new_name and new_name.strip():
                            prompts[new_name.strip()] = "Создай короткие поисковые запросы для изображений к тексту."
                            save_custom_prompts(prompts)
                            st.success(f"Промпт '{new_name}' создан!")
                            st.session_state.show_new_prompt = False
                            st.rerun()
                        else:
                            st.error("Введите название промпта")
                
                with col_cancel:
                    if st.button("❌ Отмена", key="cancel_new"):
                        st.session_state.show_new_prompt = False
                        st.rerun()
            
            # Удаление промпта
            if len(prompts) > 1:
                if st.button("🗑️ Удалить"):
                    st.session_state.show_delete_confirm = not st.session_state.show_delete_confirm
                    st.session_state.show_new_prompt = False
                
                if st.session_state.show_delete_confirm:
                    st.warning(f"Удалить промпт '{selected_prompt}'?")
                    col_delete, col_cancel_del = st.columns(2)
                    
                    with col_delete:
                        if st.button("✅ Да, удалить", key="confirm_delete"):
                            del prompts[selected_prompt]
                            save_custom_prompts(prompts)
                            st.success(f"Промпт '{selected_prompt}' удален!")
                            st.session_state.show_delete_confirm = False
                            st.rerun()
                    
                    with col_cancel_del:
                        if st.button("❌ Отмена", key="cancel_delete"):
                            st.session_state.show_delete_confirm = False
                            st.rerun()
            else:
                st.info("Нельзя удалить последний промпт")
        
        # Настройки поиска
        st.subheader("🔍 Поиск изображений")
        
        # Режим выбора поисковиков
        search_mode = st.radio(
            "Режим поиска",
            options=["Один поисковик", "Множественный выбор", "🚧 SearXNG эксклюзивный (WIP)"],
            help="Выберите режим поиска изображений"
        )
        
        if search_mode == "Один поисковик":
            # Безопасное получение индекса для selectbox
            current_engine = st.session_state.settings.get("search_engine", "duckduckgo")
            if isinstance(current_engine, list):
                current_engine = current_engine[0] if current_engine else "duckduckgo"
            
            available_engines = ["duckduckgo", "pixabay", "pinterest", "searxng", "tenor"]
            try:
                default_index = available_engines.index(current_engine)
            except ValueError:
                default_index = 0
            
            search_engine = st.selectbox(
                "Поисковик",
                options=available_engines,
                index=default_index
            )
        elif search_mode == "Множественный выбор":
            # Безопасное получение значений по умолчанию для multiselect
            current_engines = st.session_state.settings.get("search_engine", ["duckduckgo", "pixabay"])
            if isinstance(current_engines, str):
                current_engines = [current_engines]
            elif not isinstance(current_engines, list):
                current_engines = ["duckduckgo", "pixabay"]
            
            search_engines = st.multiselect(
                "Выберите поисковики",
                options=["duckduckgo", "pixabay", "pinterest", "searxng", "tenor"],
                default=current_engines,
                help="Результаты будут объединены из всех выбранных поисковиков"
            )
            search_engine = search_engines if search_engines else ["duckduckgo"]
        else:  # SearXNG эксклюзивный (WIP)
            search_engine = "searxng"
            
            # Предупреждение о статусе WIP
            st.warning("⚠️ **Режим в разработке (WIP)**: Возможны дублирующиеся результаты. Костыль дедупликации готов к применению - см. `MANUAL_DEDUP_INSTRUCTIONS.md`")
            
            # Упрощенный интерфейс для SearXNG
            col_url, col_link = st.columns([3, 1])
            
            with col_url:
                searxng_url = st.text_input(
                    "URL SearXNG сервера",
                    value=st.session_state.settings.get("searxng_url", "http://localhost:8080"),
                    help="URL вашего SearXNG сервера (локальный: http://localhost:8080)"
                )
            
            with col_link:
                st.write("")  # Отступ для выравнивания
                if st.button("🌐 Найти инстансы", help="Открыть сайт со списком SearXNG инстансов"):
                    st.markdown("""
                    **🔗 Список SearXNG инстансов:**
                    
                    Перейдите на [searx.space](https://searx.space/) чтобы найти рабочие инстансы SearXNG.
                    
                    **💡 Как выбрать инстанс:**
                    1. Откройте [searx.space](https://searx.space/)
                    2. Выберите инстанс с зеленым статусом
                    3. Скопируйте URL и вставьте в поле выше
                    
                    **🚀 Рекомендуемые инстансы:**
                    - `http://localhost:8080` (локальный - рекомендуется)
                    - `https://searx.be`
                    - `https://searx.dresden.network`
                    - `https://search.sapti.me`
                    - `https://searx.tiekoetter.com`
                    """)
            
            # Используем общую настройку количества изображений
            image_count = st.session_state.settings.get("image_count", 4)
            
            # Информация о SearXNG
            with st.expander("ℹ️ Информация о SearXNG"):
                st.markdown("""
                **SearXNG** - это метапоисковая система с открытым исходным кодом.
                
                **Преимущества:**
                - 🔒 Приватность - не отслеживает пользователей
                - 🌐 Агрегирует результаты из множества поисковиков (Bing, Google, Yandex)
                - 🚀 Быстрый поиск изображений
                - 🆓 Бесплатное использование
                
                **🚧 Текущие проблемы (WIP):**
                - Дублирующиеся результаты в поиске
                - Костыль дедупликации готов, но требует ручного применения
                
                **🔧 Как исправить:**
                1. Откройте файл `MANUAL_DEDUP_INSTRUCTIONS.md`
                2. Следуйте пошаговой инструкции
                3. Перезапустите приложение
                
                **Как найти рабочий инстанс:**
                1. Перейдите на [searx.space](https://searx.space/)
                2. Выберите инстанс с хорошим временем отклика
                3. Проверьте, что он поддерживает поиск изображений
                
                **💡 Рекомендация:** Используйте локальный SearXNG (`http://localhost:8080`) для лучшей производительности и приватности.
                """)
        
        # Убираем ограничение - используем все запросы от LLM
        st.info("💡 Количество запросов определяется автоматически на основе ответа LLM")
        
        # Настройки количества изображений
        if search_mode == "Множественный выбор" and isinstance(search_engine, list):
            st.markdown("**🎯 Изображений для каждого поисковика:**")
            engine_counts = {}
            total_images = 0
            
            for engine in search_engine:
                count = st.slider(
                    f"{engine.title()}",
                    min_value=1,
                    max_value=10,
                    value=st.session_state.settings.get(f"{engine}_count", 3),
                    key=f"count_{engine}"
                )
                engine_counts[f"{engine}_count"] = count
                total_images += count
            
            st.info(f"Всего изображений: {total_images}")
            image_count = engine_counts
        else:
            # Получаем значение по умолчанию для слайдера
            default_count = st.session_state.settings.get("image_count", 4)
            if isinstance(default_count, dict):
                default_count = 4  # Если сохранен словарь, используем значение по умолчанию
            
            image_count = st.number_input(
                "Общее количество изображений",
                min_value=1,
                max_value=100,
                value=default_count,
                step=1,
                help="Общее количество изображений, которое будет распределено между всеми запросами"
            )
        
        # Дополнительные настройки
        st.subheader("🛠️ Дополнительно")
        smart_queries = st.checkbox(
            "Умная генерация запросов",
            value=st.session_state.settings["smart_queries"]
        )
        
        url_parsing = st.checkbox(
            "Парсинг URL из текста",
            value=st.session_state.settings["url_parsing"]
        )
        
        split_long = st.checkbox(
            "Разделять длинные абзацы",
            value=st.session_state.settings["split_long_paragraphs"]
        )
        
        debug_mode = st.checkbox(
            "🐛 Режим отладки LLM",
            value=st.session_state.settings.get("debug_mode", False),
            help="Показывать сырые ответы от LLM для отладки"
        )
        
        # Сохраняем настройки при изменении
        new_settings = {
            "llm_url": llm_url,
            "llm_model": llm_model,
            "llm_api_key": llm_api_key,
            "search_engine": search_engine,
            "image_count": image_count,
            "smart_queries": smart_queries,
            "url_parsing": url_parsing,
            "split_long_paragraphs": split_long,
            "debug_mode": debug_mode,
            "system_prompt": edited_prompt,
            "search_language": st.session_state.settings["search_language"],
            "searxng_url": searxng_url if search_mode == "SearXNG эксклюзивный" else st.session_state.settings.get("searxng_url", "http://localhost:8080")
        }
        
        # Добавляем индивидуальные настройки для поисковиков
        if isinstance(image_count, dict):
            new_settings.update(image_count)
        
        if new_settings != st.session_state.settings:
            st.session_state.settings = new_settings
            save_settings(new_settings)
    
    # Основной интерфейс
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.header("📝 Ввод текста")
        text_input = st.text_area(
            "Вставьте текст для анализа:",
            height=300,
            placeholder="Вставьте здесь текст, который нужно проиллюстрировать изображениями..."
        )
        
        if st.button("🔍 Анализировать текст", type="primary", disabled=not text_input):
            if not text_input.strip():
                st.error("Введите текст для анализа")
                return
            
            # Разделяем текст на абзацы
            paragraphs = split_text_into_paragraphs(
                text_input, 
                st.session_state.settings["split_long_paragraphs"]
            )
            
            if not paragraphs:
                st.error("Не удалось разделить текст на абзацы")
                return
            
            # Инициализируем результаты в session_state
            if 'processing_results' not in st.session_state:
                st.session_state.processing_results = []
            
            # Очищаем предыдущие результаты
            st.session_state.processing_results = []
            
            # Обрабатываем каждый абзац динамически
            progress_bar = st.progress(0)
            status_text = st.empty()
            results_container = st.container()
            
            for i, paragraph in enumerate(paragraphs):
                status_text.text(f"Обрабатываем абзац {i+1} из {len(paragraphs)}...")
                progress_bar.progress((i + 1) / len(paragraphs))
                
                # Обрабатываем абзац
                result = process_paragraph(paragraph, st.session_state.settings)
                result['paragraph_index'] = i
                st.session_state.processing_results.append(result)
                
                # Показываем результат сразу
                with results_container:
                    display_paragraph_result(result, i, st.session_state.settings)
            
            results = st.session_state.processing_results
            
            # Сохраняем в историю
            total_images = sum(len(r["images"]) + len(r["url_images"]) for r in results)
            save_to_history(
                text_input,
                len(paragraphs),
                total_images,
                st.session_state.settings["search_engine"],
                st.session_state.settings["search_language"]
            )
            
            # Создаем HTML отчет
            html_file = create_html_report(results, st.session_state.settings)
            
            # Отображаем результаты
            st.success(f"✅ Обработано {len(paragraphs)} абзацев, найдено {total_images} изображений")
            
            if html_file and os.path.exists(html_file):
                with open(html_file, 'r', encoding='utf-8') as f:
                    html_content = f.read()
                
                st.download_button(
                    label="📄 Скачать HTML отчет",
                    data=html_content,
                    file_name=f"visual_analysis_{int(time.time())}.html",
                    mime="text/html"
                )
            
            # Результаты уже отображены динамически выше
            status_text.text("✅ Обработка завершена!")
            progress_bar.progress(1.0)
    
    with col2:
        st.header("📊 История")
        history = load_history()
        
        if history:
            for entry in history[:10]:  # Показываем последние 10 записей
                with st.expander(f"📅 {entry['timestamp']}"):
                    st.text(f"Текст: {entry['text_preview']}")
                    st.text(f"Абзацев: {entry['paragraphs_count']}")
                    st.text(f"Изображений: {entry['images_count']}")
                    st.text(f"Поисковик: {entry['search_engine']}")
        else:
            st.info("История пуста")
        
        # Кнопка очистки истории
        if st.button("🗑️ Очистить историю"):
            try:
                if os.path.exists(HISTORY_FILE):
                    os.remove(HISTORY_FILE)
                st.success("История очищена")
                st.rerun()
            except Exception as e:
                st.error(f"Ошибка очистки истории: {e}")

def display_paragraph_result(result: Dict, index: int, settings: Dict):
    """Отображение результата обработки абзаца с кнопкой 'Заново'"""
    with st.expander(f"📄 Абзац {index+1} ({len(result['images'])} изображений)", expanded=True):
        col1, col2 = st.columns([4, 1])
        
        with col1:
            st.text(result["text"])
        
        with col2:
            if st.button("🔄 Заново", key=f"retry_{index}"):
                # Повторная обработка абзаца
                with st.spinner("Повторная обработка..."):
                    new_result = process_paragraph(result["text"], settings)
                    new_result['paragraph_index'] = index
                    
                    # Обновляем результат в session_state
                    st.session_state.processing_results[index] = new_result
                    st.rerun()
        
        if result["queries"]:
            st.markdown("**🔍 Поисковые запросы:**")
            for query in result["queries"]:
                st.code(query)
        else:
            st.warning("⚠️ Поисковые запросы не сгенерированы. Проверьте настройки LLM.")
        
        if result["images"]:
            st.markdown("**🖼️ Найденные изображения:**")
            cols = st.columns(min(len(result["images"]), 4))
            
            for j, img in enumerate(result["images"]):
                with cols[j % 4]:
                    try:
                        st.image(img["url"], caption=f"Запрос: {img['query']}")
                        st.caption(f"Источник: {img['search_engine']}")
                    except:
                        st.error(f"Ошибка загрузки изображения: {img['url']}")

if __name__ == "__main__":
    main()