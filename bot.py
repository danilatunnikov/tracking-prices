import asyncio
import logging
import os
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramUnauthorizedError
from aiogram.types import BotCommand
from aiohttp import web
from dotenv import load_dotenv
from config import BOT_TOKEN, CHECK_INTERVAL, BOT_COMMANDS
from database import init_db, get_all_items, update_price, get_setting, update_setting
from parser import get_price
from handlers import router

load_dotenv()


class CustomFormatter(logging.Formatter):
    """Кастомный форматирщик логов с эмодзи для удобства чтения в Docker/Render"""

    grey = "\x1b[38;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"

    FORMATS = {
        logging.DEBUG: grey + "⚙️ [DEBUG] %(asctime)s - %(message)s" + reset,
        logging.INFO: "ℹ️ [INFO] %(asctime)s - %(message)s",
        logging.WARNING: yellow + "⚠️ [WARN] %(asctime)s - %(message)s" + reset,
        logging.ERROR: red + "❌ [ERROR] %(asctime)s - %(message)s" + reset,
        logging.CRITICAL: bold_red + "🚨 [CRIT] %(asctime)s - %(filename)s:%(lineno)d - %(message)s" + reset
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno, "%%(message)s")
        formatter = logging.Formatter(log_fmt, datefmt="%Y-%m-%d %H:%M:%S")
        return formatter.format(record)


# Настройка логгера
handler = logging.StreamHandler()
handler.setFormatter(CustomFormatter())
logging.basicConfig(level=logging.INFO, handlers=[handler])
logger = logging.getLogger(__name__)
# ----------------------------

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
dp.include_router(router)


async def handle_health_check(request):
    return web.Response(text="Бот успешно запущен и работает в Docker!", status=200)


async def start_health_server():
    app = web.Application()
    app.router.add_get('/', handle_health_check)
    runner = web.AppRunner(app)
    await runner.setup()

    port = int(os.getenv("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"🌐 Фоновый Health-Check сервер запущен на порту {port}")


async def set_bot_commands():
    commands = [
        BotCommand(command=cmd, description=desc)
        for cmd, desc in BOT_COMMANDS.items()
    ]
    await bot.set_my_commands(commands)
    logger.info("✅ Команды меню успешно обновлены")


async def check_prices():
    """Фоновая задача: парсинг и обновление цен"""
    logger.info("🔄 Скан цен: Запуск глобальной проверки цен по всей БД...")

    items = await get_all_items()
    if not items:
        logger.info("📋 Скан цен: База данных пуста, нечего проверять.")
        return

    updated_count = 0
    for item in items:
        try:
            current_price = await get_price(item['url'])
            if current_price is None:
                logger.warning(f"🔎 Ошибка парсинга: Не удалось получить цену для {item['url'][:40]}")
                continue

            price_changed = await update_price(item['url'], current_price)

            if price_changed:
                old_price = item['last_price']

                if old_price is None:
                    emoji, direction = "🆕", "Первая цена"
                elif current_price < old_price:
                    emoji, direction = "🔥", "Цена упала"
                elif current_price > old_price:
                    emoji, direction = "⬆️", "Цена выросла"
                else:
                    emoji, direction = "💹", "Цена изменилась"

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
                    logger.info(f"✉️ Уведомление отправлено пользователю {item['user_id']} ({direction})")

                except Exception as e:
                    logger.error(f"✉️ Ошибка отправки сообщения пользователю {item['user_id']}: {e}")

            updated_count += 1
            logger.info(f"📊 Обработан [{updated_count}/{len(items)}]: {item['url'][:30]}... -> {current_price} BYN")

        except Exception as e:
            logger.error(f"💥 Критическая ошибка при обработке {item['url'][:40]}: {e}")

        # Небольшая задержка, чтобы не спамить сайты запросами
        await asyncio.sleep(2)

    # Сохраняем дату текущей успешной проверки в базу данных
    await update_setting("last_check_date", datetime.now().isoformat())
    logger.info("🎉 Глобальная проверка цен успешно завершена и дата обновлена!")


async def scheduled_check():
    """Фоновый цикл проверки условий времени"""
    logger.info("⏰ Планировщик контроля цен успешно запущен")
    while True:
        try:
            last_check_str = await get_setting("last_check_date")

            should_check = False

            if last_check_str is None:
                logger.info("📅 Планировщик: Первичный запуск бота или запись отсутствует. Требуется проверка!")
                should_check = True
            else:
                last_check_time = datetime.fromisoformat(last_check_str)
                # Если с момента последней проверки прошло больше 24 часов
                if datetime.now() - last_check_time >= timedelta(days=1):
                    logger.info(
                        f"📅 Планировщик: С прошлой проверки прошло более 24 часов (Последняя: {last_check_time.strftime('%Y-%m-%d %H:%M')}). Запускаем!")
                    should_check = True
                else:
                    time_left = timedelta(days=1) - (datetime.now() - last_check_time)
                    hours_left = int(time_left.total_seconds() // 3600)
                    minutes_left = int((time_left.total_seconds() % 3600) // 60)
                    logger.info(
                        f"💤 Планировщик: До следующей проверки цен осталось примерно {hours_left}ч {minutes_left}м.")

            if should_check:
                await check_prices()

        except Exception as e:
            logger.error(f"🚨 Ошибка в цикле планировщика: {e}")

        await asyncio.sleep(CHECK_INTERVAL)


async def main():
    logger.info("🚀 СТАРТ: Инициализация всех систем бота...")

    await init_db()
    await set_bot_commands()

    # Запуск веб-сервера для Render
    asyncio.create_task(start_health_server())

    # Запуск бесконечного планировщика проверки цен
    asyncio.create_task(scheduled_check())

    try:
        logger.info("🤖 Bot Polling запущен. Ожидание сообщений...")
        await dp.start_polling(bot)
    except TelegramUnauthorizedError:
        logger.critical("❌ Авторизация провалена: Неверный токен BOT_TOKEN!")
    except Exception as e:
        logger.critical(f"❌ Непредвиденная ошибка в основном цикле: {e}")
    finally:
        await bot.session.close()
        logger.info("🛑 Бот полностью остановлен")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Процесс завершен пользователем (KeyboardInterrupt)")