import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramUnauthorizedError
from aiogram.types import BotCommand
from aiohttp import web
from dotenv import load_dotenv
from config import BOT_TOKEN, CHECK_INTERVAL, BOT_COMMANDS
from database import init_db, get_all_items, update_price
from parser import get_price
from handlers import router

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
dp.include_router(router)

async def handle_health_check(request):
    """Возвращает статус 200 для Render, чтобы контейнер не падал"""
    return web.Response(text="Бот успешно запущен и работает в Docker!", status=200)


async def start_health_server():
    """Запускает фоновый веб-сервер на порту от Render"""
    app = web.Application()
    app.router.add_get('/', handle_health_check)
    runner = web.AppRunner(app)
    await runner.setup()

    # Render передает порт в переменную PORT. Если запускаешь локально — включится 10000
    port = int(os.getenv("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"🌐 Фоновый Health-Check сервер запущен на порту {port}")
async def set_bot_commands():
    """Настраивает команды в меню бота"""
    commands = [
        BotCommand(command=cmd, description=desc)
        for cmd, desc in BOT_COMMANDS.items()
    ]
    await bot.set_my_commands(commands)
    logger.info("✅ Команды бота настроены")


async def check_prices():
    """Фоновая задача: проверка цен"""
    logger.info("🔄 Запуск проверки цен...")

    items = await get_all_items()
    for item in items:
        try:
            current_price = await get_price(item['url'])
            if current_price is None:
                continue

            price_changed = await update_price(item['url'], current_price)

            if price_changed:
                old_price = item['last_price']

                if old_price is None:
                    emoji = "🆕"
                    direction = "Первая цена"
                elif current_price < old_price:
                    emoji = "🔥"
                    direction = "Цена упала"
                elif current_price > old_price:
                    emoji = "⬆️"
                    direction = "Цена выросла"
                else:
                    emoji = "💹"
                    direction = "Цена изменилась"

                try:
                    message_text = f"{emoji} {direction}!\n\n"
                    message_text += f"📦 Товар: {item['url'][:50]}...\n"

                    if old_price:
                        message_text += (
                            f"💰 Было: {old_price:.2f} BYN\n"
                            f"💰 Стало: {current_price:.2f} BYN\n"
                            f"{'💸 Выгода' if current_price < old_price else '💰 Переплата'}: {abs(current_price - old_price):.2f} BYN\n"
                        )
                    else:
                        message_text += f"💰 Цена: {current_price:.2f} BYN\n"

                    await bot.send_message(item['user_id'], message_text)

                except Exception as e:
                    logger.error(f"Не удалось отправить уведомление: {e}")

            logger.info(f"✅ {item['url'][:30]}... = {current_price} BYN")

        except Exception as e:
            logger.error(f"Ошибка проверки {item['url']}: {e}")

        await asyncio.sleep(2)

    logger.info("✅ Проверка цен завершена")


async def scheduled_check():
    """Бесконечный цикл проверки"""
    while True:
        await check_prices()
        await asyncio.sleep(CHECK_INTERVAL)


async def main():
    logger.info("🚀 Запуск бота...")

    await init_db()
    await set_bot_commands()  # Настраиваем команды

    asyncio.create_task(start_health_server())

    asyncio.create_task(scheduled_check())
    try:
        await dp.start_polling(bot)
    except TelegramUnauthorizedError:
        logger.error("❌ Неверный токен бота!")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
    finally:
        await bot.session.close()
        logger.info("🛑 Бот остановлен")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Остановка пользователем")