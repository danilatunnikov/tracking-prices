import asyncio

import aiohttp
from typing import Optional
from bs4 import BeautifulSoup
from config import HEADERS, REQUEST_TIMEOUT, ALLOWED_DOMAINS
from urllib.parse import urlparse
from utils import make_callback_key
import hashlib


async def is_safe_url(url: str) -> bool:
    """Проверка безопасности ссылки"""
    try:
        parsed = urlparse(url)
        if parsed.scheme != 'https':
            return False
        # Проверка домена из белого списка
        return any(domain in parsed.netloc for domain in ALLOWED_DOMAINS)
    except Exception:
        return False


async def fetch_page(url: str) -> Optional[str]:
    """Скачивание страницы с защитой"""
    print(f"🔍 Проверяю URL: {url}")

    if not await is_safe_url(url):
        print(f"❌ URL не в белом списке!")
        return None

    try:
        print(f"📡 Отправляю запрос к {url}...")
        async with aiohttp.ClientSession() as session:
            async with session.get(
                    url,
                    headers=HEADERS,
                    timeout=REQUEST_TIMEOUT,
                    allow_redirects=True
            ) as response:
                print(f"📡 Статус ответа: {response.status}")
                # print(f"📡 Заголовки: {dict(response.headers)}")

                if response.status == 200:
                    html = await response.text()
                    print(f"✅ Страница загружена, размер: {len(html)} байт")
                    return html
                elif response.status == 403:
                    print("❌ 403 Forbidden — сайт блокирует запрос")
                elif response.status == 404:
                    print("❌ 404 Not Found — страница не существует")
                else:
                    print(f"❌ Ошибка HTTP {response.status}")

    except asyncio.TimeoutError:
        print(f"⏱ Таймаут — сайт не ответил за {REQUEST_TIMEOUT} сек")
    except aiohttp.ClientConnectorError as e:
        print(f"🌐 Ошибка подключения: {e}")
    except Exception as e:
        print(f"💥 Неожиданная ошибка: {type(e).__name__}: {e}")

    return None


def parse_price_1kby(html: str) -> Optional[float]:
    """Парсинг для 1k.by — ищем цену в нескольких местах"""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'lxml')

    # Пробуем разные селекторы (сайты меняют вёрстку)
    selectors = [
        ('div', {'class': 'spec-about__price'}),
        ('span', {'class': 'product-price'}),
        ('meta', {'itemprop': 'price'}),
        ('div', {'data-price': True}),
        ('span', {'class': 'price-value'}),
        ('span', {'class': 'price'}),
    ]

    for tag_name, attrs in selectors:
        elem = soup.find(tag_name, attrs)
        if elem:
            # Для <meta> берём content, для остальных — текст
            text = elem.get('content') or elem.get_text(strip=True)
            return clean_price(text)

    # Fallback: ищем цену регуляркой во всём тексте страницы
    text = soup.get_text()
    return clean_price(text)


def parse_price_shopby(html: str) -> Optional[float]:
    """Парсинг для shop.by"""
    soup = BeautifulSoup(html, 'lxml')

    # Находим основной элемент с ценой
    price_block = soup.find('span', class_='PriceBlock__PriceValue')

    if price_block:
        # Находим все span внутри и берём второй (индекс 1)
        spans = price_block.find_all('span')
        if len(spans) >= 2:
            price_text = spans[1].get_text(strip=True)
            return clean_price(price_text)

    return None

def parse_price_5element(html: str) -> Optional[float]:
    soup = BeautifulSoup(html, 'lxml')

    price_block = soup.find('div', class_='p-price__actual')

    if price_block:
        text = price_block.get_text(strip=True)
        print(text)
        return clean_price(text)

    return None


def get_product_name_1kby(html: str) -> Optional[str]:
    """Извлечение названия товара для 1k.by"""
    soup = BeautifulSoup(html, 'lxml')

    # Ищем h1 внутри div.heading
    heading_div = soup.find('div', class_='heading')
    if heading_div:
        h1_tag = heading_div.find('h1')
        if h1_tag:
            name = h1_tag.get_text(strip=True)
            print(f"🏷 1k.by название: {name}")
            return name

    # Fallback: ищем просто h1 на странице
    h1_tag = soup.find('h1')
    if h1_tag:
        name = h1_tag.get_text(strip=True)
        print(f"🏷 1k.by название (fallback): {name}")
        return name

    print("⚠️ 1k.by название не найдено")
    return None


def get_product_name_shopby(html: str) -> Optional[str]:
    """Извлечение названия товара для shop.by"""
    soup = BeautifulSoup(html, 'lxml')

    # Ищем h1
    h1_tag = soup.find('h1', class_='Page__TitleActivePage', itemprop='name')
    if h1_tag:
        name = h1_tag.get_text(strip=True)
        print(f"🏷 Название: {name}")
        return name

    return None


def get_product_name_5element(html: str) -> Optional[str]:
    """Извлечение названия товара для 5element.by"""
    soup = BeautifulSoup(html, 'lxml')

    # Ищем h1 внутри div.heading
    heading_div = soup.find('div', class_='heading')
    if heading_div:
        h1_tag = heading_div.find('h1')
        if h1_tag:
            name = h1_tag.get_text(strip=True)
            print(f"🏷 Название: {name}")
            return name

    # Fallback: ищем просто h1 на странице
    h1_tag = soup.find('h1')
    if h1_tag:
        name = h1_tag.get_text(strip=True)
        print(f"🏷 Название (fallback): {name}")
        return name

    return None


def get_product_name(url: str, html: str) -> Optional[str]:
    """Главная функция для получения названия товара"""
    from urllib.parse import urlparse
    domain = urlparse(url).netloc

    if '5element.by' in domain:
        return get_product_name_5element(html)
    elif '1k.by' in domain:
        return get_product_name_1kby(html)
    elif 'shop.by' in domain:
        return get_product_name_shopby(html)
    else:
        # Универсальный парсер
        soup = BeautifulSoup(html, 'lxml')
        h1_tag = soup.find('h1')
        if h1_tag:
            return h1_tag.get_text(strip=True)
        return None

def parse_price_generic(html: str) -> Optional[float]:
    """Универсальный парсер (ищет любые цифры с валютой)"""
    import re
    soup = BeautifulSoup(html, 'lxml')
    text = soup.get_text()
    # Ищем паттерны типа "1 200 руб", "1200.00 BYN"
    matches = re.findall(r'(\d[\d\s]*\.?\d*)\s*(?:руб|BYN|Br|₽)', text, re.IGNORECASE)
    if matches:
        return clean_price(matches[0])
    return None


def clean_price(text: str) -> Optional[float]:
    """
    Извлекает минимальную цену из текста.
    Поддерживает: '3 183,10 – 3 970,00 б.р.', '1200.00 BYN', '999 руб'
    """
    import re
    if not text:
        return None

    # Ищем все числа с разделителями (пробел/запятая/точка)
    # Паттерн: одна или более цифр, возможно с разделителями тысяч и десятичными
    pattern = r'(\d+(?:[\s\.]?\d{3})*(?:[,.]\d+)?)'
    matches = re.findall(pattern, text)

    if not matches:
        return None

    # Берём первое найденное число (минимальное в диапазоне)
    price_str = matches[0]

    # Удаляем пробелы (разделители тысяч) и заменяем запятую на точку
    price_str = price_str.replace(' ', '').replace(',', '.')

    try:
        return float(price_str)
    except ValueError:
        return None


async def get_price(url: str) -> Optional[float]:
    html = await fetch_page(url)
    if not html:
        return None

    from urllib.parse import urlparse
    domain = urlparse(url).netloc

    if '1k.by' in domain:
        price = parse_price_1kby(html)
    elif 'shop.by' in domain:
        price = parse_price_shopby(html)
    elif '5element' in domain:
        price = parse_price_5element(html)
    else:
        price = parse_price_generic(html)

    # 🔍 Детальный лог для отладки
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"🔍 {domain}: price={price}, HTML snippet: {html[300:600] if html else 'None'}")

    return price