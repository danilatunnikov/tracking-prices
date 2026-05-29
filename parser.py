import asyncio
import aiohttp
from typing import Optional
from bs4 import BeautifulSoup
from config import HEADERS, REQUEST_TIMEOUT, ALLOWED_DOMAINS, SCRAPER_API_KEY
from urllib.parse import urlparse, quote_plus
import logging
import re

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


def is_blocked_content(html: str, url: str = "") -> tuple[bool, Optional[str]]:
    """Проверка контента на блокировку или заглушку капчи"""
    if not html:
        return True, "Пустой HTML"

    html_lower = html.lower()

    if len(html) < 5000:
        return True, f"размер HTML слишком мал ({len(html)} симв.)"

    # shop.by — мягкая проверка: их нормальный HTML содержит слова вроде
    # "блокировщик рекламы" и скрипты с "captcha", поэтому проверяем только
    # жёсткие признаки реальной блокировки
    if 'shop.by' in url:
        hard_markers = [
            "verify you are human",
            "checking your browser",
            "access denied",
            "ddos-guard",
        ]
        detected = next((m for m in hard_markers if m in html_lower), None)
        if detected:
            return True, f"найден маркер '{detected}'"
        return False, None

    # Для всех остальных сайтов — полный набор маркеров
    block_markers = [
        "captcha",
        "cloudflare",
        "робот",
        "доступ ограничен",
        "блокиров",
        "разблокировать ip",
        "checking your browser",
        "verify you are human",
        "ошибка доступа",
    ]
    detected_marker = next((m for m in block_markers if m in html_lower), None)
    if detected_marker:
        return True, f"найден маркер '{detected_marker}'"

    return False, None


async def fetch_page(url: str) -> Optional[str]:
    """
    Скачивание HTML страницы.
    Попытка 1: Напрямую.
    Попытка 2: Через ScraperAPI в случае любой ошибки или блокировки.
    """
    if not await is_safe_url(url):
        logger.warning(f"⚠️ URL не в белом списке: {url}")
        return None

    # --- ПОПЫТКА 1: Напрямую ---
    logger.info(f"📡 Запрос напрямую: {url[:50]}...")
    direct_failed = False
    html_content = None

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT, allow_redirects=True) as response:
                if response.status == 200:
                    html_content = await response.text()
                    is_blocked, reason = is_blocked_content(html_content, url)
                    if is_blocked:
                        logger.warning(
                            f"🛑 Прямой запрос заблокирован сервером ({reason}). Переключаюсь на ScraperAPI...")
                        direct_failed = True
                else:
                    logger.warning(
                        f"⚠️ Прямой запрос вернул HTTP статус {response.status}. Переключаюсь на ScraperAPI...")
                    direct_failed = True
    except Exception as e:
        logger.warning(f"🌐 Прямое подключение завершилось ошибкой ({type(e).__name__}). Переключаюсь на ScraperAPI...")
        direct_failed = True

    if not direct_failed and html_content:
        return html_content

    # --- ПОПЫТКА 2: Через ScraperAPI (без render=true — работает на бесплатном тарифе) ---
    if not SCRAPER_API_KEY:
        logger.error("❌ ScraperAPI Ключ (SCRAPER_API_KEY) отсутствует в конфигурации! Обход блокировки невозможен.")
        return None

    proxy_url = f"http://api.scraperapi.com/?api_key={SCRAPER_API_KEY}&url={quote_plus(url)}&country_code=by"
    logger.info(f"🔄 Резервный план: Отправляю запрос через ScraperAPI для {urlparse(url).netloc}...")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(proxy_url, timeout=30) as response:
                if response.status == 200:
                    html = await response.text()
                    is_blocked, reason = is_blocked_content(html, url)
                    if not is_blocked:
                        logger.info(f"🎉 ScraperAPI успешно получил оригинальный HTML!")
                        return html
                    logger.error(f"❌ Даже через ScraperAPI вернулась заглушка блокировки ({reason})")
                else:
                    logger.error(f"❌ ScraperAPI ответил с ошибкой. Статус-код: {response.status}")
    except Exception as proxy_error:
        logger.error(f"💥 Критическая ошибка при работе со ScraperAPI: {proxy_error}")

    return None


def extract_price_from_text(text: str) -> Optional[float]:
    """Извлекает минимальную (первую) цену из текстовой строки"""
    if not text:
        return None

    pattern = r'(\d+(?:[\s\.]?\d{3})*(?:[,.]\d+)?)'
    matches = re.findall(pattern, text)
    if not matches:
        return None

    price_str = matches[0].replace(' ', '').replace(',', '.')
    try:
        val = float(price_str)
        # Отсекаем явно нецелевые значения (артикулы, рейтинги и т.д.)
        if val < 1 or val > 1_000_000:
            return None
        return val
    except ValueError:
        return None


def _parse_price_from_description(description: str) -> Optional[float]:
    """
    Извлекает цену из meta description.
    Ищет паттерн 'от X XXX,XX руб.' или просто первое большое число.
    """
    if not description:
        return None

    # Паттерн: "от 3 640,00 руб." или "3640.00"
    match = re.search(r'от\s+([\d\s]+[,.][\d]+)\s*руб', description)
    if match:
        return extract_price_from_text(match.group(1))

    # Запасной: любое число больше 100 (цена товара)
    matches = re.findall(r'(\d[\d\s]*[,.]\d{2})', description)
    for m in matches:
        val = extract_price_from_text(m)
        if val and val > 100:
            return val

    return None


async def get_price(url: str) -> Optional[float]:
    """Получение и парсинг цены товара по точной структуре сайтов"""
    html = await fetch_page(url)
    if not html:
        return None

    domain = urlparse(url).netloc
    soup = BeautifulSoup(html, "html.parser")

    try:
        if '1k.by' in domain:
            # Основной: <div class="spec-about__price">
            price_element = soup.find("div", class_="spec-about__price")
            if price_element:
                return extract_price_from_text(price_element.get_text(strip=True))

            price_block = soup.find("div", class_="spec-about__prices")
            if price_block:
                price_element = price_block.find("div", class_="spec-about__price")
                if price_element:
                    return extract_price_from_text(price_element.get_text(strip=True))

            # Резервно: schema.org meta
            for itemprop in ("price", "lowPrice"):
                price_meta = soup.find("meta", {"itemprop": itemprop})
                if price_meta and price_meta.get("content"):
                    try:
                        return float(price_meta["content"])
                    except ValueError:
                        pass

        elif 'shop.by' in domain:
            # Основной: span с классом PriceBlock__PriceValue (варианты регистра)
            for cls in ("PriceBlock__PriceValue", "PriceBlock__priceValue", "PriceBlock__price-value"):
                price_element = soup.find("span", class_=cls)
                if price_element:
                    val = extract_price_from_text(price_element.get_text(strip=True))
                    if val:
                        return val

            # Резервно: span.price__value
            price_element = soup.find("span", class_="price__value")
            if price_element:
                val = extract_price_from_text(price_element.get_text(strip=True))
                if val:
                    return val

            # Резервно: schema.org meta
            price_meta = soup.find("meta", {"itemprop": "price"})
            if price_meta and price_meta.get("content"):
                try:
                    return float(price_meta["content"])
                except ValueError:
                    pass

            # Последний резерв: парсим цену из meta description
            # (там shop.by пишет "от 3 640,00 руб." даже когда JS не отрендерен)
            desc_meta = soup.find("meta", {"name": "description"})
            if desc_meta and desc_meta.get("content"):
                val = _parse_price_from_description(desc_meta["content"])
                if val:
                    logger.info(f"💡 shop.by: цена получена из meta description: {val}")
                    return val

    except Exception as e:
        logger.error(f"💥 Ошибка разбора HTML-структуры цен для {url[:40]}...: {e}")

    return None


async def get_product_name(url: str) -> str:
    """Получение названия товара для инициализации в БД"""
    html = await fetch_page(url)
    if not html:
        return "Отслеживаемый товар"

    soup = BeautifulSoup(html, "html.parser")
    try:
        h1 = soup.find("h1")
        if h1:
            return h1.text.strip()

        meta_title = soup.find("meta", {"property": "og:title"})
        if meta_title and meta_title.get("content"):
            return meta_title["content"].strip()
    except Exception:
        pass

    return "Товар с " + urlparse(url).netloc