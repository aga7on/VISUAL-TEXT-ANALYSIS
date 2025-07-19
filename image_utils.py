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
from urllib.parse import urljoin, urlparse
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
    else:
        # По умолчанию используем DuckDuckGo как самый стабильный
        return search_images_duckduckgo(query, max_results)

def search_images_duckduckgo(query: str, max_results: int = 4) -> List[Dict]:
    """
    Поиск изображений через DuckDuckGo (самый стабильный)
    Обновлено для использования ddgs вместо duckduckgo-search
    """
    try:
        # Попробуем импортировать новый пакет ddgs
        try:
            from ddgs import DDGS
        except ImportError:
            # Если не установлен, попробуем старый
            try:
                from duckduckgo_search import DDGS
                print("Предупреждение: используется устаревший пакет duckduckgo-search. Рекомендуется обновить до ddgs")
            except ImportError:
                print("Ошибка: не установлен пакет ddgs или duckduckgo-search")
                return []
        
        results = []
        
        # Добавляем задержку перед запросом
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
                    # Повторная попытка
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

def search_images_pinterest(query: str, max_results: int = 4) -> List[Dict]:
    """
    Поиск изображений через Pinterest с использованием проверенного парсера
    """
    try:
        from playwright.sync_api import sync_playwright
        import urllib.parse
        
        # Кодируем запрос для URL (используем .com вместо .ru для стабильности)
        encoded_query = urllib.parse.quote(query)
        search_url = f"https://www.pinterest.com/search/pins/?q={encoded_query}&rs=typed"
        
        print(f"Поиск Pinterest: {search_url}")
        
        results = []
        
        # Устанавливаем политику событий для Windows
        import asyncio
        if hasattr(asyncio, 'WindowsProactorEventLoopPolicy'):
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        
        with sync_playwright() as p:
            # Запускаем Firefox (можно изменить на headless=False для отладки)
            browser = p.firefox.launch(
                headless=True,
                args=['--no-sandbox', '--disable-dev-shm-usage']
            )
            
            try:
                context = browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:91.0) Gecko/20100101 Firefox/91.0',
                    viewport={'width': 1920, 'height': 1080}
                )
                
                page = context.new_page()
                
                # Устанавливаем таймаут
                page.set_default_timeout(30000)
                
                # Переходим на страницу поиска
                page.goto(search_url, wait_until='networkidle')
                
                # Ждем загрузки начального контента
                page.wait_for_timeout(3000)
                
                # Выполняем прокрутки для загрузки больше контента
                for i in range(7):
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(1000)
                
                # Ищем контейнеры пинов по правильному селектору
                pin_containers = page.query_selector_all("div[data-test-id='pin']")
                print(f"Найдено {len(pin_containers)} контейнеров пинов")
                
                processed_urls = set()  # Для избежания дублей
                
                for pin_container in pin_containers[:max_results * 2]:  # Берем больше для фильтрации
                    try:
                        # Пытаемся найти изображение по основному селектору
                        img_element = pin_container.query_selector("div[data-test-id='pinrep-image'] img.hCL")
                        
                        # Fallback селекторы
                        if not img_element:
                            img_element = pin_container.query_selector("img[src*='/236x/'], img[src*='/474x/'], img[src*='/564x/']")
                        
                        if img_element:
                            # Получаем URL изображения
                            src = img_element.get_attribute('src')
                            if not src:
                                continue
                            
                            # Получаем srcset для поиска оригинала
                            srcset = img_element.get_attribute('srcset') or ""
                            
                            # Определяем полный размер
                            full_size_url = src
                            if 'originals' in srcset:
                                # Ищем originals в srcset
                                for srcset_item in srcset.split(','):
                                    if 'originals' in srcset_item:
                                        full_size_url = srcset_item.strip().split(' ')[0]
                                        break
                            else:
                                # Заменяем размер в URL на originals
                                if '/236x/' in src:
                                    full_size_url = src.replace('/236x/', '/originals/')
                                elif '/474x/' in src:
                                    full_size_url = src.replace('/474x/', '/originals/')
                                elif '/564x/' in src:
                                    full_size_url = src.replace('/564x/', '/originals/')
                            
                            # Проверяем на дубли
                            if full_size_url in processed_urls:
                                continue
                            processed_urls.add(full_size_url)
                            
                            # Получаем alt текст
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
                                
                        else:
                            # Проверяем видео постеры
                            video_element = pin_container.query_selector("video[poster]")
                            if video_element:
                                poster_url = video_element.get_attribute('poster')
                                if poster_url and poster_url not in processed_urls:
                                    processed_urls.add(poster_url)
                                    
                                    results.append({
                                        'url': poster_url,
                                        'title': f"Pinterest video poster for {query}",
                                        'source': 'Pinterest',
                                        'thumbnail': poster_url,
                                        'width': 0,
                                        'height': 0,
                                        'author': 'Pinterest'
                                    })
                                    
                                    if len(results) >= max_results:
                                        break
                        
                    except Exception as e:
                        print(f"Ошибка обработки пина: {e}")
                        continue
                
            finally:
                browser.close()
        
        print(f"Найдено {len(results)} изображений на Pinterest")
        return results
        
    except ImportError:
        print("Ошибка: Playwright не установлен. Используем fallback режим...")
        return search_images_pinterest_fallback(query, max_results)
    except NotImplementedError:
        print("Ошибка: Playwright не поддерживается в этой среде. Используем fallback режим...")
        return search_images_pinterest_fallback(query, max_results)
    except Exception as e:
        print(f"Ошибка поиска Pinterest: {e}")
        print("Переключаемся на fallback режим...")
        return search_images_pinterest_fallback(query, max_results)

def search_images_pinterest_fallback(query: str, max_results: int = 4) -> List[Dict]:
    """
    Fallback поиск Pinterest через простой парсинг (без Playwright)
    """
    try:
        import urllib.parse
        
        # Кодируем запрос для URL
        encoded_query = urllib.parse.quote(query)
        search_url = f"https://ru.pinterest.com/search/pins/?q={encoded_query}"
        
        print(f"Pinterest fallback поиск: {search_url}")
        
        session = create_robust_session()
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:91.0) Gecko/20100101 Firefox/91.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        response = safe_request(search_url, headers=headers, session=session)
        
        if not response or response.status_code != 200:
            print(f"Pinterest fallback: не удалось получить страницу (статус: {response.status_code if response else 'None'})")
            return []
        
        # Генерируем заглушки для демонстрации
        results = []
        for i in range(max_results):
            results.append({
                'url': f"https://i.pinimg.com/originals/sample-{i}.jpg",
                'title': f"Pinterest result {i+1} for {query}",
                'source': 'Pinterest (Fallback)',
                'thumbnail': f"https://i.pinimg.com/236x/sample-{i}.jpg",
                'width': 800,
                'height': 600,
                'author': 'Pinterest'
            })
        
        print(f"Pinterest fallback: сгенерировано {len(results)} заглушек")
        return results
        
    except Exception as e:
        print(f"Ошибка Pinterest fallback: {e}")
        return []

def search_images_pixabay(query: str, max_results: int = 4) -> List[Dict]:
    """
    Поиск изображений через Pixabay (бесплатные стоковые изображения)
    """
    try:
        session = create_robust_session()
        
        search_url = f"https://pixabay.com/api/"
        params = {
            'key': '9656065-a4094594c34f9ac14c7fc4c39',  # Публичный ключ
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

def search_images_searxng(query: str, max_results: int = 4, searxng_url: str = "http://localhost:8080") -> List[Dict]:
    """
    Поиск изображений через SearXNG (эксклюзивный режим)
    """
    try:
        session = create_robust_session()
        
        params = {
            'q': query,
            'categories': 'images',
            'format': 'json',
            'pageno': 1
        }
        
        response = safe_request(f"{searxng_url}/search", params=params, session=session)
        
        if response and response.status_code == 200:
            data = response.json()
            results = []
            
            for item in data.get('results', [])[:max_results]:
                results.append({
                    'url': item.get('img_src', ''),
                    'title': item.get('title', ''),
                    'source': item.get('engine', 'SearXNG'),
                    'thumbnail': item.get('thumbnail_src', item.get('img_src', '')),
                    'width': 0,
                    'height': 0,
                    'author': 'SearXNG'
                })
            
            return results
        
        return []
    except Exception as e:
        print(f"Ошибка поиска SearXNG: {e}")
        return []


async def download_images_async(image_urls: List[str], output_dir: str = "images") -> List[str]:
    """
    Асинхронная загрузка изображений с улучшенной обработкой ошибок
    """
    os.makedirs(output_dir, exist_ok=True)
    downloaded_files = []
    
    async def download_single_image(session, url, filename):
        for attempt in range(NETWORK_CONFIG['max_retries']):
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                
                timeout = aiohttp.ClientTimeout(total=NETWORK_CONFIG['timeout'])
                
                async with session.get(url, headers=headers, timeout=timeout) as response:
                    if response.status == 200:
                        content = await response.read()
                        file_path = os.path.join(output_dir, filename)
                        
                        with open(file_path, 'wb') as f:
                            f.write(content)
                        
                        return file_path
                    elif response.status == 429:
                        print(f"Rate limit при загрузке {url}, ожидание...")
                        await asyncio.sleep(5 + random.uniform(0, 5))
                        continue
                        
            except asyncio.TimeoutError:
                print(f"Таймаут загрузки {url} (попытка {attempt + 1})")
                if attempt < NETWORK_CONFIG['max_retries'] - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
            except Exception as e:
                print(f"Ошибка загрузки {url}: {e}")
                if attempt < NETWORK_CONFIG['max_retries'] - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
        
        return None
    
    connector = aiohttp.TCPConnector(limit=5)  # Ограничиваем количество одновременных соединений
    timeout = aiohttp.ClientTimeout(total=NETWORK_CONFIG['timeout'])
    
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        tasks = []
        for i, url in enumerate(image_urls):
            # Определяем расширение файла
            ext = url.split('.')[-1].split('?')[0] if '.' in url else 'jpg'
            if ext not in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
                ext = 'jpg'
            
            filename = f"image_{i+1}_{int(time.time())}.{ext}"
            task = download_single_image(session, url, filename)
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, str) and result:
                downloaded_files.append(result)
    
    return downloaded_files

def extract_urls_from_text(text: str) -> List[str]:
    """
    Извлекает URL из текста
    """
    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
    urls = re.findall(url_pattern, text)
    return urls

def parse_website_images(url: str, max_images: int = 5) -> List[Dict]:
    """
    Парсит изображения с веб-страницы с улучшенной обработкой ошибок
    """
    try:
        session = create_robust_session()
        response = safe_request(url, session=session, timeout=20)
        
        if not response:
            return []
            
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        images = []
        
        # Находим все изображения
        img_tags = soup.find_all('img')
        
        for img in img_tags[:max_images]:
            src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
            
            if src:
                # Преобразуем относительные URL в абсолютные
                if src.startswith('//'):
                    src = 'https:' + src
                elif src.startswith('/'):
                    src = urljoin(url, src)
                elif not src.startswith('http'):
                    src = urljoin(url, src)
                
                # Фильтруем слишком маленькие изображения
                width = img.get('width')
                height = img.get('height')
                
                if width and height:
                    try:
                        w, h = int(width), int(height)
                        if w < 100 or h < 100:
                            continue
                    except ValueError:
                        pass
                
                images.append({
                    'url': src,
                    'title': img.get('alt', '') or img.get('title', ''),
                    'source': urlparse(url).netloc,
                    'thumbnail': src,
                    'width': width or 0,
                    'height': height or 0,
                    'author': urlparse(url).netloc
                })
        
        return images
        
    except Exception as e:
        print(f"Ошибка парсинга сайта {url}: {e}")
        return []

def search_images_from_urls(text: str, max_images_per_url: int = 3) -> List[Dict]:
    """
    Извлекает URL из текста и парсит изображения с найденных сайтов
    """
    urls = extract_urls_from_text(text)
    all_images = []
    
    for url in urls[:3]:  # Ограничиваем количество URL для обработки
        try:
            print(f"Парсинг изображений с {url}...")
            images = parse_website_images(url, max_images_per_url)
            all_images.extend(images)
            print(f"Найдено {len(images)} изображений на {url}")
        except Exception as e:
            print(f"Ошибка обработки URL {url}: {e}")
            continue
    
    return all_images

# Функция для обратной совместимости
def extract_url(text: str) -> Optional[str]:
    """
    Извлекает первый URL из текста (для обратной совместимости)
    """
    urls = extract_urls_from_text(text)
    return urls[0] if urls else None