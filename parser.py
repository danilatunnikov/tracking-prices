# import asyncio
# import aiohttp
# from typing import Optional
# from bs4 import BeautifulSoup
# from config import HEADERS, REQUEST_TIMEOUT, ALLOWED_DOMAINS
# from urllib.parse import urlparse
# import logging
#
# # Используем логгер, настроенный в bot.py
# logger = logging.getLogger(__name__)
#
#
# async def is_safe_url(url: str) -> bool:
#     """Проверка безопасности ссылки"""
#     try:
#         parsed = urlparse(url)
#         if parsed.scheme != 'https':
#             return False
#         # Проверка домена из белого списка
#         return any(domain in parsed.netloc for domain in ALLOWED_DOMAINS)
#     except Exception:
#         return False
#
#
# async def fetch_page(url: str) -> Optional[str]:
#     """Скачивание страницы с защитой от блокировок и заглушек"""
#     if not await is_safe_url(url):
#         logger.warning(f"⚠️ URL не в белом списке: {url}")
#         return None
#
#     try:
#         async with aiohttp.ClientSession() as session:
#             async with session.get(
#                     url,
#                     headers=HEADERS,
#                     timeout=REQUEST_TIMEOUT,
#                     allow_redirects=True
#             ) as response:
#
#                 if response.status != 200:
#                     logger.warning(f"⚠️ Ошибка HTTP {response.status} при запросе к {url[:40]}...")
#                     return None
#
#                 html = await response.text()
#
#                 # --- ПРОВЕРКА НА БЛОКИРОВКУ / ЗАГЛУШКУ ---
#                 html_lower = html.lower()
#
#                 # Ключевые маркеры страниц блокировок и капчи
#                 block_markers = [
#                     "captcha",
#                     "cloudflare",
#                     "робот",
#                     "доступ ограничен",
#                     "блокиров",
#                     "checking your browser",
#                     "verify you are human"
#                 ]
#
#                 # Ищем маркер в тексте страницы
#                 detected_marker = next((m for m in block_markers if m in html_lower), None)
#
#                 # Если страница подозрительно короткая (страницы капчи обычно весят мало)
#                 is_too_short = len(html) < 5000
#
#                 if detected_marker or is_too_short:
#                     reason = f"найден маркер '{detected_marker}'" if detected_marker else f"размер HTML всего {len(html)} симв."
#                     logger.warning(f"🛑 ЗАГЛУШКА ИЛИ БЛОКИРОВКА ({reason}) на URL: {url}")
#                     return None
#                 # ----------------------------------------
#
#                 return html
#
#     except aiohttp.ClientError as e:
#         logger.error(f"🌐 Ошибка сети при запросе к {url[:40]}...: {e}")
#     except Exception as e:
#         logger.error(f"💥 Ошибка скачивания страницы {url[:40]}...: {e}")
#
#     return None
#
#
# def extract_price_from_text(text: str) -> Optional[float]:
#     """
#     Извлекает минимальную цену из текста.
#     Поддерживает: '3 183,10 – 3 970,00 б.р.', '1200.00 BYN', '999 руб'
#     """
#     import re
#     if not text:
#         return None
#
#     # Ищем все числа с разделителями (пробел/запятая/точка)
#     pattern = r'(\d+(?:[\s\.]?\d{3})*(?:[,.]\d+)?)'
#     matches = re.findall(pattern, text)
#
#     if not matches:
#         return None
#
#     # Берём первое найденное число (минимальное в диапазоне)
#     price_str = matches[0]
#
#     # Удаляем пробелы (разделители тысяч) и заменяем запятую на точку
#     price_str = price_str.replace(' ', '').replace(',', '.')
#
#     try:
#         return float(price_str)
#     except ValueError:
#         return None
#
#
# async def get_price(url: str) -> Optional[float]:
#     """Получение и парсинг цены товара"""
#     html = await fetch_page(url)
#     if not html:
#         # Если fetch_page вернул None (из-за ошибки или блокировки), сразу выходим
#         return None
#
#     domain = urlparse(url).netloc
#     soup = BeautifulSoup(html, "html.parser")
#
#     try:
#         if '1k.by' in domain:
#             # Парсинг для 1k.by
#             price_element = soup.find("span", class_="price") or soup.find("div", class_="price")
#             if price_element:
#                 return extract_price_from_text(price_element.text)
#
#             # Альтернативный поиск по контенту, если верстка немного отличается
#             alt_price = soup.find(meta={"property": "product:price:amount"})
#             if alt_price:
#                 return float(alt_price["content"])
#
#         elif 'shop.by' in domain:
#             # Парсинг для shop.by
#             price_element = soup.find("span", class_="price__value") or soup.find("span",
#                                                                                   class_="PriceBlock__priceValue")
#             if price_element:
#                 return extract_price_from_text(price_element.text)
#
#             price_meta = soup.find(meta={"itemprop": "price"})
#             if price_meta:
#                 return float(price_meta["content"])
#
#     except Exception as e:
#         logger.error(f"💥 Ошибка разбора HTML структуры для {url[:40]}...: {e}")
#
#     return None
#
#
# async def get_product_name(url: str) -> str:
#     """Получение названия товара для инициализации в БД"""
#     html = await fetch_page(url)
#     if not html:
#         return "Неизвестный товар (Ошибка загрузки)"
#
#     soup = BeautifulSoup(html, "html.parser")
#
#     try:
#         # Пробуем стандартный тег h1
#         h1 = soup.find("h1")
#         if h1:
#             return h1.text.strip()
#
#         # Пробуем OpenGraph тег заголовка
#         meta_title = soup.find(meta={"property": "og:title"})
#         if meta_title:
#             return meta_title["content"].strip()
#
#     except Exception:
#         pass
#
#     return "Товар без названия"
import asyncio
import aiohttp
from typing import Optional
from bs4 import BeautifulSoup
from config import HEADERS, REQUEST_TIMEOUT, ALLOWED_DOMAINS, SCRAPER_API_KEY
from urllib.parse import urlparse, quote_plus
import logging

logger = logging.getLogger(__name__)


async def is_safe_url(url: str) -> bool:
    """Проверка безопасности ссылки"""
    try:
        parsed = urlparse(url)
        if parsed.scheme != 'https':
            return False
        return any(domain in parsed.netloc for domain in ALLOWED_DOMAINS)
    except Exception:
        return False


def is_blocked_content(html: str) -> tuple[bool, Optional[str]]:
    """
    Внутренняя утилита для проверки контента на блокировку.
    Возвращает (True, причина), если обнаружена блокировка.
    """
    html_lower = html.lower()

    # Ключевые маркеры страниц блокировок и капчи
    block_markers = [
        "captcha",
        "cloudflare",
        "робот",
        "доступ ограничен",
        "блокиров",
        "checking your browser",
        "verify you are human"
    ]

    detected_marker = next((m for m in block_markers if m in html_lower), None)
    if detected_marker:
        return True, f"найден маркер '{detected_marker}'"

    if len(html) < 5000:
        return True, f"размер HTML слишком мал ({len(html)} симв.)"

    return False, None


async def fetch_page(url: str) -> Optional[str]:
    """
    Скачивание страницы.
    Попытка 1: Напрямую.
    Попытка 2 (резервная): Через ScraperAPI, если первая попытка заблокирована или упала по ошибке.
    """
    if not await is_safe_url(url):
        logger.warning(f"⚠️ URL не в белом списке: {url}")
        return None

    # --- ПОПЫТКА 1: Напрямую без прокси ---
    logger.info(f"📡 Запрос напрямую: {url[:50]}...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT, allow_redirects=True) as response:
                if response.status == 200:
                    html = await response.text()
                    is_blocked, reason = is_blocked_content(html)

                    if not is_blocked:
                        return html  # Успех напрямую!

                    logger.warning(f"🛑 Прямой запрос заблокирован ({reason}). Переключаюсь на ScraperAPI...")
                else:
                    logger.warning(f"⚠️ Прямой запрос вернул статус {response.status}. Переключаюсь на ScraperAPI...")
    except Exception as e:
        logger.warning(f"🌐 Ошибка прямого подключения ({type(e).__name__}). Пробуем через ScraperAPI...")

    # --- ПОПЫТКА 2: Через ScraperAPI (Резервный план) ---
    if not SCRAPER_API_KEY:
        logger.error("❌ ScraperAPI Ключ (SCRAPER_API_KEY) не найден в конфигурации! Пропуск прокси.")
        return None

    # Формируем URL запроса к прокси по документации ScraperAPI
    # quote_plus кодирует символы вроде / и : чтобы их понял API
    proxy_url = f"http://api.scraperapi.com/?api_key={SCRAPER_API_KEY}&url={quote_plus(url)}"

    logger.info(f"🔄 Попытка через ScraperAPI для: {url[:40]}...")
    try:
        # Для ScraperAPI таймаут лучше взять побольше (около 30 сек), так как они внутри себя могут перебирать прокси
        async with aiohttp.ClientSession() as session:
            async with session.get(proxy_url, timeout=30) as response:
                if response.status == 200:
                    html = await response.text()
                    is_blocked, reason = is_blocked_content(html)

                    if not is_blocked:
                        logger.info(f"🎉 ScraperAPI успешно обошел блокировку для {url[:40]}!")
                        return html

                    logger.error(f"❌ Даже ScraperAPI вернул заглушку блокировки ({reason})")
                else:
                    logger.error(f"❌ Ошибка ScraperAPI. Статус-код: {response.status}")
    except Exception as e:
        logger.error(f"💥 Критическая ошибка при запросе через ScraperAPI: {e}")

    return None


def extract_price_from_text(text: str) -> Optional[float]:
    """Извлекает минимальную цену из текста"""
    import re
    if not text:
        return None

    pattern = r'(\d+(?:[\s\.]?\\d{3})*(?:[,.]\d+)?)'
    matches = re.findall(pattern, text)

    if not matches:
        return None

    price_str = matches[0]
    price_str = price_str.replace(' ', '').replace(',', '.')

    try:
        return float(price_str)
    except ValueError:
        return None


async def get_price(url: str) -> Optional[float]:
    """Получение и парсинг цены товара"""
    html = await fetch_page(url)
    if not html:
        return None

    domain = urlparse(url).netloc
    soup = BeautifulSoup(html, "html.parser")

    try:
        if '1k.by' in domain:
            price_element = soup.find("span", class_="price") or soup.find("div", class_="price")
            if price_element:
                return extract_price_from_text(price_element.text)

            alt_price = soup.find(meta={"property": "product:price:amount"})
            if alt_price:
                return float(alt_price["content"])

        elif 'shop.by' in domain:
            price_element = soup.find("span", class_="price__value") or soup.find("span",
                                                                                  class_="PriceBlock__priceValue")
            if price_element:
                return extract_price_from_text(price_element.text)

            price_meta = soup.find(meta={"itemprop": "price"})
            if price_meta:
                return float(price_meta["content"])

    except Exception as e:
        logger.error(f"💥 Ошибка разбора HTML структуры для {url[:40]}...: {e}")

    return None


async def get_product_name(url: str) -> str:
    """Получение названия товара для инициализации в БД"""
    html = await fetch_page(url)
    if not html:
        return "Неизвестный товар (Ошибка загрузки)"

    soup = BeautifulSoup(html, "html.parser")
    try:
        h1 = soup.find("h1")
        if h1:
            return h1.text.strip()

        meta_title = soup.find(meta={"property": "og:title"})
        if meta_title:
            return meta_title["content"].strip()
    except Exception:
        pass

    return "Товар без названия"