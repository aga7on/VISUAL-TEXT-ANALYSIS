# -*- coding: utf-8 -*-
"""
Улучшенный модуль для поиска и загрузки изображений
Добавлена устойчивость к сетевым ошибкам и нестабильному интернету
"""

import re
import asyncio
import aiohttp
import requests
import os
import time
import random
import json
from urllib.parse import urljoin, urlparse, quote
from bs4 import BeautifulSoup
from typing import List, Dict, Optional, Union
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Настройки для устойчивости к сетевым ошибкам
NETWORK_CONFIG = {
    'timeout': 30,  # Увеличенный таймаут
    'max_retries': 3,  # Количество повторных попыток
    'backoff_factor': 1,  # Фактор экспоненциального отката
    'retry_statuses': [429, 500, 502, 503, 504],  # Статусы для повтора
    'delay_between_requests': 1,  # Задержка между запросами в секундах
}

def create_robust_session():
    """
    Создает сессию requests с настройками для устойчивости к сетевым ошибкам
    """
    session = requests.Session()
    
    # Настройка retry стратегии
    retry_strategy = Retry(
        total=NETWORK_CONFIG['max_retries'],
        status_forcelist=NETWORK_CONFIG['retry_statuses'],
        backoff_factor=NETWORK_CONFIG['backoff_factor'],
        raise_on_status=False
    )
    
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    return session

def safe_request(url, headers=None, params=None, timeout=None, session=None):
    """
    Безопасный запрос с обработкой ошибок и повторными попытками
    """
    if session is None:
        session = create_robust_session()
    
    if timeout is None:
        timeout = NETWORK_CONFIG['timeout']
    
    if headers is None:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
    
    for attempt in range(NETWORK_CONFIG['max_retries'] + 1):
        try:
            # Добавляем случайную задержку для избежания rate limiting
            if attempt > 0:
                delay = NETWORK_CONFIG['delay_between_requests'] * (2 ** attempt) + random.uniform(0, 1)
                print(f"Попытка {attempt + 1}, ожидание {delay:.1f} сек...")
                time.sleep(delay)
            
            response = session.get(url, headers=headers, params=params, timeout=timeout)
            
            if response.status_code == 200:
                return response
            elif response.status_code == 429:  # Rate limit
                print(f"Rate limit (429), ожидание перед повтором...")
                time.sleep(5 + random.uniform(0, 5))
                continue
            elif response.status_code in NETWORK_CONFIG['retry_statuses']:
                print(f"Ошибка {response.status_code}, повторная попытка...")
                continue
            else:
                print(f"Ошибка HTTP {response.status_code}")
                return None
                
        except requests.exceptions.Timeout:
            print(f"Таймаут соединения (попытка {attempt + 1})")
            if attempt < NETWORK_CONFIG['max_retries']:
                continue
        except requests.exceptions.ConnectionError:
            print(f"Ошибка соединения (попытка {attempt + 1})")
            if attempt < NETWORK_CONFIG['max_retries']:
                continue
        except Exception as e:
            print(f"Неожиданная ошибка: {e}")
            if attempt < NETWORK_CONFIG['max_retries']:
                continue
    
    return None

def search_images(query: str, max_results: int = 4, search_engine: Union[str, List[str]] = "duckduckgo", searxng_url: str = "http://localhost:8080") -> List[Dict]:
    """
    Универсальная функция поиска изображений
    Поддерживает множественный выбор поисковиков и SearXNG
    """
    # Если передан список поисковиков, объединяем результаты
    if isinstance(search_engine, list):
        all_results = []
        results_per_engine = max(1, max_results // len(search_engine))
        
        for engine in search_engine:
            try:
                print(f"Поиск через {engine}...")
                results = search_images_single(query, results_per_engine, engine, searxng_url)
                all_results.extend(results)
                print(f"Найдено {len(results)} изображений через {engine}")
            except Exception as e:
                print(f"Ошибка поиска в {engine}: {e}")
                continue
        
        return all_results[:max_results]
    
    # Одиночный поисковик
    return search_images_single(query, max_results, search_engine, searxng_url)

def search_images_single(query: str, max_results: int = 4, search_engine: str = "duckduckgo", searxng_url: str = "http://localhost:8080") -> List[Dict]:
    """
    Поиск изображений через один поисковик
    """
    if search_engine == "duckduckgo":
        return search_images_duckduckgo(query, max_results)
    elif search_engine == "pixabay":
        return search_images_pixabay(query, max_results)
    elif search_engine == "pinterest":
        return search_images_pinterest(query, max_results)
    elif search_engine == "searxng":
        return search_images_searxng(query, max_results, searxng_url)
    elif search_engine == "tenor":
        return search_images_tenor(query, max_results)
    else:
        # По умолчанию используем DuckDuckGo как самый стабильный
        return search_images_duckduckgo(query, max_results)

def search_images_duckduckgo(query: str, max_results: int = 4) -> List[Dict]:
    """
    Поиск изображений через DuckDuckGo (самый стабильный)
    """
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            try:
                from duckduckgo_search import DDGS
                print("Предупреждение: используется устаревший пакет duckduckgo-search")
            except ImportError:
                print("Ошибка: не установлен пакет ddgs или duckduckgo-search")
                return []
        
        results = []
        time.sleep(NETWORK_CONFIG['delay_between_requests'])
        
        with DDGS() as ddgs:
            try:
                ddgs_images_gen = ddgs.images(
                    query,
                    max_results=max_results,
                    safesearch="moderate"
                )
                
                for r in ddgs_images_gen:
                    results.append({
                        'url': r.get('image', ''),
                        'title': r.get('title', ''),
                        'source': r.get('source', ''),
                        'thumbnail': r.get('thumbnail', ''),
                        'width': r.get('width', 0),
                        'height': r.get('height', 0),
                        'author': 'DuckDuckGo'
                    })
                    
            except Exception as e:
                if "202" in str(e) and "Ratelimit" in str(e):
                    print("DuckDuckGo rate limit, ожидание...")
                    time.sleep(10 + random.uniform(0, 5))
                    try:
                        ddgs_images_gen = ddgs.images(
                            query,
                            max_results=max_results,
                            safesearch="moderate"
                        )
                        
                        for r in ddgs_images_gen:
                            results.append({
                                'url': r.get('image', ''),
                                'title': r.get('title', ''),
                                'source': r.get('source', ''),
                                'thumbnail': r.get('thumbnail', ''),
                                'width': r.get('width', 0),
                                'height': r.get('height', 0),
                                'author': 'DuckDuckGo'
                            })
                    except Exception as e2:
                        print(f"Повторная ошибка DuckDuckGo: {e2}")
                        raise e2
                else:
                    raise e
                
        return results
    except Exception as e:
        print(f"Ошибка поиска DuckDuckGo: {e}")
        return []

def search_images_pixabay(query: str, max_results: int = 4) -> List[Dict]:
    """
    Поиск изображений через Pixabay
    """
    try:
        session = create_robust_session()
        
        search_url = f"https://pixabay.com/api/"
        params = {
            'key': '9656065-a4094594c34f9ac14c7fc4c39',
            'q': query,
            'image_type': 'photo',
            'per_page': max_results,
            'safesearch': 'true'
        }
        
        response = safe_request(search_url, params=params, session=session)
        
        if response and response.status_code == 200:
            data = response.json()
            results = []
            
            for hit in data.get('hits', [])[:max_results]:
                results.append({
                    'url': hit.get('webformatURL', ''),
                    'title': hit.get('tags', ''),
                    'source': 'Pixabay',
                    'thumbnail': hit.get('previewURL', ''),
                    'width': hit.get('webformatWidth', 0),
                    'height': hit.get('webformatHeight', 0),
                    'author': hit.get('user', 'Pixabay')
                })
            
            return results
        
        return []
    except Exception as e:
        print(f"Ошибка поиска Pixabay: {e}")
        return []

def search_images_pinterest(query: str, max_results: int = 4) -> List[Dict]:
    """
    Pinterest поиск с fallback
    """
    try:
        from playwright.sync_api import sync_playwright
        import urllib.parse
        
        encoded_query = urllib.parse.quote(query)
        search_url = f"https://www.pinterest.com/search/pins/?q={encoded_query}&rs=typed"
        
        print(f"Поиск Pinterest: {search_url}")
        results = []
        
        import asyncio
        if hasattr(asyncio, 'WindowsProactorEventLoopPolicy'):
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        
        with sync_playwright() as p:
            browser = p.firefox.launch(headless=True)
            try:
                context = browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:91.0) Gecko/20100101 Firefox/91.0'
                )
                page = context.new_page()
                page.set_default_timeout(30000)
                page.goto(search_url, wait_until='networkidle')
                page.wait_for_timeout(3000)
                
                for i in range(7):
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(1000)
                
                pin_containers = page.query_selector_all("div[data-test-id='pin']")
                processed_urls = set()
                
                for pin_container in pin_containers[:max_results * 2]:
                    try:
                        img_element = pin_container.query_selector("div[data-test-id='pinrep-image'] img.hCL")
                        if not img_element:
                            img_element = pin_container.query_selector("img[src*='/236x/'], img[src*='/474x/']")
                        
                        if img_element:
                            src = img_element.get_attribute('src')
                            if not src:
                                continue
                            
                            full_size_url = src
                            if '/236x/' in src:
                                full_size_url = src.replace('/236x/', '/originals/')
                            elif '/474x/' in src:
                                full_size_url = src.replace('/474x/', '/originals/')
                            
                            if full_size_url in processed_urls:
                                continue
                            processed_urls.add(full_size_url)
                            
                            img_alt = img_element.get_attribute('alt') or f"Pinterest image for {query}"
                            
                            results.append({
                                'url': full_size_url,
                                'title': img_alt,
                                'source': 'Pinterest',
                                'thumbnail': src,
                                'width': 0,
                                'height': 0,
                                'author': 'Pinterest'
                            })
                            
                            if len(results) >= max_results:
                                break
                                
                    except Exception as e:
                        continue
                
            finally:
                browser.close()
        
        return results
        
    except Exception as e:
        print(f"Ошибка поиска Pinterest: {e}")
        return []

def search_images_searxng(query: str, max_results: int = 4, searxng_url: str = "http://localhost:8080") -> List[Dict]:
    """
    ИСПРАВЛЕННЫЙ SearXNG поиск - использует HTML парсинг (ПРОТЕСТИРОВАНО И РАБОТАЕТ!)
    Ключевое исправление: НЕ используем format=json, парсим HTML
    """
    print(f"🔍 SearXNG поиск: '{query}' через {searxng_url}")
    
    # Проверенные рабочие инстансы + локальный
    urls_to_try = []
    
    # Если указан пользовательский URL, пробуем его первым
    if searxng_url:
        urls_to_try.append(searxng_url)
    
    # Добавляем публичные инстансы как fallback (только если не localhost)
    if searxng_url != "http://localhost:8080":
        public_instances = [
            "https://searx.be",
            "https://searx.dresden.network", 
            "https://search.sapti.me",
            "https://searx.tiekoetter.com"
        ]
        urls_to_try.extend(public_instances)
    
    for attempt, base_url in enumerate(urls_to_try):
        try:
            print(f"🌐 Попытка {attempt + 1}: {base_url}")
            
            if attempt > 0:
                time.sleep(1 + random.uniform(0, 2))
            
            # Простые заголовки (работают лучше чем сложные)
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            # КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ: НЕ используем format=json (вызывает 403 Forbidden)
            search_params = {
                'q': query,
                'categories': 'images'
                # format=json УБРАН - это была причина проблемы!
            }
            
            search_url = f"{base_url.rstrip('/')}/search"
            print(f"📡 HTML запрос: {search_url}")
            
            response = requests.get(search_url, params=search_params, headers=headers, timeout=20)
            print(f"📊 Ответ: {response.status_code}")
            
            if response.status_code == 200:
                # Парсим HTML вместо JSON
                soup = BeautifulSoup(response.text, 'html.parser')
                results = []
                processed_urls = set()
                
                print(f"✅ HTML получен, размер: {len(response.text)} символов")
                
                # Ищем все img теги
                img_tags = soup.find_all('img')
                print(f"🖼️ Найдено img тегов: {len(img_tags)}")
                
                for img in img_tags:
                    try:
                        # Получаем все возможные URL
                        urls_to_check = []
                        if img.get('src') and img.get('src').startswith('http'):
                            urls_to_check.append(img.get('src'))
                        if img.get('data-src') and img.get('data-src').startswith('http'):
                            urls_to_check.append(img.get('data-src'))
                        
                        # Берем первый уникальный URL
                        img_src = None
                        for url in urls_to_check:
                            url_base = url.split('?')[0]
                            if url not in processed_urls and not any(url_base in r.get('url', '') for r in results):
                                img_src = url
                                break
                        
                        if img_src and img_src.startswith('http') and img_src not in processed_urls:
                            # Фильтруем служебные изображения
                            skip_patterns = ['/static/', 'favicon', 'logo', '/css/', '/js/', 'searx']
                            if any(pattern in img_src for pattern in skip_patterns):
                                continue
                            
                            # Фильтруем нежелательные домены
                            skip_domains = ['facebook.com', 'instagram.com', 'twitter.com', 'tiktok.com']
                            if any(domain in img_src for domain in skip_domains):
                                continue
                            
                            processed_urls.add(img_src)
                            
                            title = img.get('alt', '') or f"SearXNG result for {query}"
                            
                            # Определяем источник
                            engine = 'unknown'
                            parent = img.find_parent()
                            if parent:
                                engine_info = str(parent.get('class', []))
                                if 'bing' in engine_info.lower():
                                    engine = 'bing'
                                elif 'google' in engine_info.lower():
                                    engine = 'google'
                                elif 'yandex' in engine_info.lower():
                                    engine = 'yandex'
                            
                            result = {
                                'url': img_src,
                                'title': title[:100],
                                'source': f"SearXNG ({engine})",
                                'thumbnail': img_src,
                                'width': 0,
                                'height': 0,
                                'author': f"SearXNG via {engine}",
                                'engine': engine
                            }
                            
                            results.append(result)
                            print(f"   ✅ Результат {len(results)}: {engine} - {title[:30]}...")
                            
                            if len(results) >= max_results:
                                break
                    
                    except Exception:
                        continue
                
                if results:
                    print(f"🎉 SearXNG успешно: {len(results)} результатов из {base_url}")
                    return results
                else:
                    print(f"⚠️ HTML получен, но изображения не найдены")
                    
            elif response.status_code == 403:
                print(f"⚠️ Доступ запрещен на {base_url}")
                continue
            else:
                print(f"❌ HTTP {response.status_code} на {base_url}")
                continue
                
        except requests.exceptions.Timeout:
            print(f"⏰ Таймаут на {base_url}")
            continue
        except requests.exceptions.ConnectionError:
            print(f"🔌 Ошибка соединения с {base_url}")
            continue
        except Exception as e:
            print(f"❌ Ошибка с {base_url}: {e}")
            continue
    
    # НЕ используем fallback на DuckDuckGo - это маскировало проблему
    print(f"❌ SearXNG: все инстансы недоступны для запроса '{query}'")
    print(f"💡 Проверьте, что локальный SearXNG запущен на {searxng_url}")
    
    return []


def search_images_external_searxng(query: str, max_results: int = 4) -> List[Dict]:
    """
    Поиск через внешние SearXNG инстансы с обходом блокировок
    """
    print(f"🌐 Внешний SearXNG поиск: '{query}'")
    
    # Список рабочих инстансов (обновляется по мере тестирования)
    external_instances = [
        "https://searx.dresden.network",
        "https://search.sapti.me", 
        "https://searx.tiekoetter.com",
        "https://searx.fmac.xyz"
    ]
    
    results = []
    
    for attempt, instance in enumerate(external_instances):
        try:
            print(f"🌐 Попытка {attempt + 1}: {instance}")
            
            # Задержка между попытками
            if attempt > 0:
                time.sleep(2 + random.uniform(0, 3))
            
            search_url = f"{instance.rstrip('/')}/search"
            
            # Улучшенные заголовки для обхода блокировок
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Cache-Control': 'max-age=0'
            }
            
            # Пробуем HTML парсинг (более надежно чем JSON)
            html_params = {
                'q': query,
                'categories': 'images',
                'language': 'en'
            }
            
            response = requests.get(search_url, params=html_params, headers=headers, timeout=20)
            print(f"📊 Ответ: {response.status_code}")
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                img_tags = soup.find_all('img')
                processed_urls = set()
                
                print(f"✅ HTML получен, размер: {len(response.text)} символов")
                print(f"🖼️ Найдено img тегов: {len(img_tags)}")
                
                for img in img_tags:
                    if len(results) >= max_results:
                        break
                        
                    src = img.get('src') or img.get('data-src')
                    if src and src.startswith('http') and src not in processed_urls:
                        # Фильтруем служебные изображения
                        skip_patterns = ['/static/', 'favicon', 'logo', 'searx', '/css/', '/js/', '/assets/']
                        if any(pattern in src for pattern in skip_patterns):
                            continue
                        
                        # Фильтруем нежелательные домены
                        skip_domains = ['facebook.com', 'instagram.com', 'twitter.com', 'tiktok.com']
                        if any(domain in src for domain in skip_domains):
                            continue
                        
                        processed_urls.add(src)
                        
                        title = img.get('alt') or img.get('title') or f'External SearXNG result for {query}'
                        
                        # Определяем источник по URL
                        engine = 'unknown'
                        if 'bing.net' in src or 'bing.com' in src:
                            engine = 'bing'
                        elif 'googleusercontent.com' in src or 'gstatic.com' in src:
                            engine = 'google'
                        elif 'yandex' in src:
                            engine = 'yandex'
                        elif 'wikipedia' in src:
                            engine = 'wikipedia'
                        
                        result = {
                            'url': src,
                            'title': title[:100],
                            'source': f"External SearXNG ({engine})",
                            'thumbnail': src,
                            'width': 0,
                            'height': 0,
                            'author': f"External SearXNG via {engine}",
                            'engine': engine
                        }
                        
                        results.append(result)
                        print(f"   ✅ Результат {len(results)}: {engine} - {title[:30]}...")
                
                if results:
                    print(f"🎉 Внешний SearXNG успешно: {len(results)} результатов из {instance}")
                    return results
                else:
                    print(f"⚠️ HTML получен, но изображения не найдены")
                    
            elif response.status_code == 403:
                print(f"⚠️ Доступ запрещен на {instance}")
                continue
            elif response.status_code == 429:
                print(f"⚠️ Rate limit на {instance}")
                continue
            else:
                print(f"❌ HTTP {response.status_code} на {instance}")
                continue
                
        except requests.exceptions.Timeout:
            print(f"⏰ Таймаут на {instance}")
            continue
        except requests.exceptions.ConnectionError:
            print(f"🔌 Ошибка соединения с {instance}")
            continue
        except Exception as e:
            print(f"❌ Ошибка с {instance}: {e}")
            continue
    
    print(f"❌ Все внешние SearXNG инстансы недоступны для запроса '{query}'")
    return []


def search_images_tenor(query: str, max_results: int = 4) -> List[Dict]:
    """
    Улучшенная функция поиска GIF/WebP/MP4 на Tenor.com
    Использует множественные методы парсинга включая API
    """
    results = []
    encoded_query = quote(query)
    
    # Метод 1: Попытка использовать Tenor API v2
    try:
        api_url = "https://tenor.googleapis.com/v2/search"
        api_params = {
            'q': query,
            'key': 'AIzaSyAyimkuYQYF_FXVALexPuGQctUWRURdCYQ',  # Публичный ключ
            'limit': max_results,
            'media_filter': 'gif,webp'
        }
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(api_url, params=api_params, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if 'results' in data:
                for item in data['results'][:max_results]:
                    media_formats = item.get('media_formats', {})
                    
                    # Приоритет: gif > webp > mp4
                    for format_name in ['gif', 'webp', 'mp4']:
                        if format_name in media_formats:
                            format_data = media_formats[format_name]
                            if isinstance(format_data, dict) and 'url' in format_data:
                                results.append({
                                    'url': format_data['url'],
                                    'title': item.get('content_description', f'Tenor {format_name} for {query}'),
                                    'source': 'Tenor',
                                    'thumbnail': format_data['url'],
                                    'width': format_data.get('dims', [0, 0])[0],
                                    'height': format_data.get('dims', [0, 0])[1],
                                    'author': 'Tenor',
                                    'type': format_name
                                })
                                break
                
                if results:
                    print(f"✅ Tenor API v2: найдено {len(results)} результатов")
                    return results[:max_results]
    
    except Exception as e:
        print(f"Tenor API v2 недоступен: {e}")
    
    # Метод 2: Альтернативный API endpoint
    try:
        alt_api_url = f"https://tenor.com/api/v1/search"
        alt_params = {
            'q': query,
            'key': 'LIVDSRZULELA',
            'limit': max_results
        }
        
        response = requests.get(alt_api_url, params=alt_params, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if 'results' in data:
                for item in data['results'][:max_results]:
                    media_formats = item.get('media_formats', {})
                    
                    for format_name in ['gif', 'webp', 'mp4', 'tinygif']:
                        if format_name in media_formats:
                            format_data = media_formats[format_name]
                            if isinstance(format_data, dict) and 'url' in format_data:
                                results.append({
                                    'url': format_data['url'],
                                    'title': item.get('title', f'Tenor {format_name} for {query}'),
                                    'source': 'Tenor',
                                    'thumbnail': format_data['url'],
                                    'width': format_data.get('dims', [0, 0])[0],
                                    'height': format_data.get('dims', [0, 0])[1],
                                    'author': 'Tenor',
                                    'type': format_name
                                })
                                break
                
                if results:
                    print(f"✅ Tenor API v1: найдено {len(results)} результатов")
                    return results[:max_results]
    
    except Exception as e:
        print(f"Tenor API v1 недоступен: {e}")
    
    # Метод 3: HTML парсинг с улучшенными селекторами
    try:
        search_urls = [
            f"https://tenor.com/search/{encoded_query}-gifs",
            f"https://tenor.com/ru/search/{encoded_query}-gifs"
        ]
        
        session = create_robust_session()
        
        for search_url in search_urls:
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'ru,en;q=0.9',
                    'Referer': 'https://tenor.com/',
                    'DNT': '1',
                    'Connection': 'keep-alive'
                }
                
                response = safe_request(search_url, headers=headers, session=session)
                
                if response and response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    processed_urls = set()
                    
                    # Поиск различными методами
                    selectors = [
                        'img[src*="tenor.com"]',
                        'img[src*="media.tenor.com"]',
                        'img[data-src*="tenor.com"]',
                        'video[src*="tenor.com"]'
                    ]
                    
                    for selector in selectors:
                        elements = soup.select(selector)
                        
                        for element in elements:
                            src = element.get('src') or element.get('data-src')
                            
                            if src and src not in processed_urls and 'tenor' in src:
                                # Пропускаем служебные изображения
                                if any(skip in src for skip in ['/assets/', 'logo', 'icon']):
                                    continue
                                    
                                processed_urls.add(src)
                                
                                # Определяем тип медиа
                                media_type = 'gif'
                                if '.webp' in src:
                                    media_type = 'webp'
                                elif '.mp4' in src:
                                    media_type = 'mp4'
                                elif element.name == 'video':
                                    media_type = 'video'
                                
                                results.append({
                                    'url': src,
                                    'title': element.get('alt') or element.get('title') or f'Tenor {media_type} for {query}',
                                    'source': 'Tenor',
                                    'thumbnail': src,
                                    'width': 0,
                                    'height': 0,
                                    'author': 'Tenor',
                                    'type': media_type
                                })
                                
                                if len(results) >= max_results:
                                    break
                        
                        if len(results) >= max_results:
                            break
                    
                    # Поиск в JavaScript коде
                    if len(results) < max_results:
                        scripts = soup.find_all('script')
                        for script in scripts:
                            script_text = script.get_text()
                            if script_text and ('tenor.com' in script_text or 'media.tenor.com' in script_text):
                                # Ищем JSON данные с URL
                                json_patterns = [
                                    r'"url":"(https://[^"]*tenor\.com[^"]*\.(?:gif|webp|mp4)[^"]*)"',
                                    r'"gif":\s*\{[^}]*"url":"([^"]*)"',
                                    r'"webp":\s*\{[^}]*"url":"([^"]*)"'
                                ]
                                
                                for pattern in json_patterns:
                                    matches = re.findall(pattern, script_text)
                                    for match in matches:
                                        if match not in processed_urls and 'tenor' in match:
                                            processed_urls.add(match)
                                            
                                            media_type = 'gif'
                                            if '.webp' in match:
                                                media_type = 'webp'
                                            elif '.mp4' in match:
                                                media_type = 'mp4'
                                            
                                            results.append({
                                                'url': match,
                                                'title': f'Tenor {media_type} for {query}',
                                                'source': 'Tenor',
                                                'thumbnail': match,
                                                'width': 0,
                                                'height': 0,
                                                'author': 'Tenor',
                                                'type': media_type
                                            })
                                            
                                            if len(results) >= max_results:
                                                break
                                    
                                    if len(results) >= max_results:
                                        break
                                
                                if len(results) >= max_results:
                                    break
                    
                    if results:
                        print(f"✅ Tenor HTML: найдено {len(results)} результатов")
                        return results[:max_results]
                        
            except Exception as e:
                print(f"Ошибка парсинга {search_url}: {e}")
                continue
    
    except Exception as e:
        print(f"HTML парсинг не сработал: {e}")
    
    print(f"❌ Tenor: результаты не найдены для запроса '{query}'")
    return []

# Функции автопоиска SearXNG инстансов удалены для упрощения интерфейса
# Пользователи теперь выбирают инстансы вручную через https://searx.space/

# Заглушки для совместимости
def download_images_async(image_urls, output_dir="images"):
    return []

def extract_urls_from_text(text):
    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
    return re.findall(url_pattern, text)

def search_images_from_urls(text, max_images_per_url=3):
    return []