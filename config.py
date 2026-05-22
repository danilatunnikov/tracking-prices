import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

ALLOWED_DOMAINS = [
    '1k.by',
    'shop.by',
    # '5element.by',
]

REQUEST_TIMEOUT = 10
CHECK_INTERVAL = 900

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}

BOT_COMMANDS = {
    "track": "🔍 Отследить цену товара",
    "my": "📦 Мои отслеживаемые товары",
    "history": "📊 История изменений цены",
    "menu": "🏠 Показать главное меню",
    "help": "❓ Помощь и информация"
}

SCRAPER_API_KEY = os.getenv("SCRAPER_API_KEY")