import hashlib
from aiogram import types, Router, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from keyboards import get_main_keyboard, get_cancel_keyboard, get_empty_keyboard, get_items_list_keyboard
from database import (
    add_item, get_user_items, delete_item,
    update_price, get_price_history, get_item_by_url
)
from parser import get_price, is_safe_url, get_product_name, fetch_page
from config import ALLOWED_DOMAINS
from utils import make_callback_key
from keyboards import get_main_keyboard, get_cancel_keyboard, get_empty_keyboard, get_items_list_keyboard, get_back_keyboard
from html import escape
from aiogram.exceptions import TelegramBadRequest

router = Router()

# --- КОМАНДЫ ---

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    """Приветствие с главным меню"""
    await message.answer(
        "👋 Привет! Я бот для отслеживания цен.\n\n"
        "Я умею:\n"
        "• 🔍 Отслеживать цены на товары\n"
        "• 📊 Показывать историю изменений\n"
        "• 🔔 Уведомлять об изменении цены\n\n"
        f"✅ Поддерживаемые магазины: {', '.join(ALLOWED_DOMAINS)}\n\n"
        "👇 Выберите действие в меню:",
        reply_markup=get_main_keyboard()
    )


@router.message(Command("menu"))
async def cmd_menu(message: types.Message):
    """Показать главное меню"""
    await message.answer(
        "🏠 Главное меню:",
        reply_markup=get_main_keyboard()
    )


@router.message(F.text == "🔍 Отследить цену")
async def btn_track(message: types.Message):
    """Кнопка «Отследить цену»"""
    await message.answer(
        "📝 Отправьте ссылку на товар:\n\n"
        f"Поддерживаемые сайты: {', '.join(ALLOWED_DOMAINS)}\n\n"
        "❌ Отмена — чтобы вернуться в меню",
        reply_markup=get_cancel_keyboard()
    )


@router.message(F.text == "📦 Мои товары")
async def btn_my(message: types.Message):
    """Кнопка «Мои товары»"""
    await cmd_my(message)


@router.message(F.text == "📊 История цен")
async def btn_history(message: types.Message):
    """Кнопка «История цен»"""
    await message.answer(
        "📝 Отправьте ссылку на товар для просмотра истории:\n\n"
        "❌ Отмена — чтобы вернуться в меню",
        reply_markup=get_cancel_keyboard()
    )


@router.message(F.text == "❓ Помощь")
async def btn_help(message: types.Message):
    """Кнопка «Помощь»"""
    await cmd_help(message)


@router.message(F.text == "❌ Отмена")
async def btn_cancel(message: types.Message):
    """Кнопка «Отмена»"""
    await message.answer(
        "❌ Отменено. Выберите действие в меню:",
        reply_markup=get_main_keyboard()
    )


@router.message(Command("track"))
async def cmd_track(message: types.Message):
    """Команда /track — запрос ссылки"""
    await message.answer(
        "📝 Отправьте ссылку на товар:\n\n"
        f"Поддерживаемые сайты: {', '.join(ALLOWED_DOMAINS)}",
        reply_markup=get_cancel_keyboard()
    )


@router.message(Command("my"))
async def cmd_my(message: types.Message):
    """Показывает список товаров с полной информацией"""
    # Получаем товары пользователя из базы
    items = await get_user_items(message.from_user.id)

    # Если товаров нет — показываем сообщение с меню
    if not items:
        await message.answer(
            "📭 У вас нет отслеживаемых товаров.\n\n"
            "Используйте кнопку «🔍 Отследить цену» чтобы добавить товар.",
            reply_markup=get_main_keyboard()
        )
        return

    # Формируем текст списка
    text = "📦 <b>Ваши товары:</b>\n\n"

    for i, item in enumerate(items, 1):
        # Статус (зелёный если есть цена, жёлтый если нет)
        status_emoji = "🟢" if item['last_price'] else "🟡"

        # Форматируем цену
        price_str = f"{item['last_price']:.2f} BYN" if item['last_price'] else "???"

        # Название товара (экранируем HTML-символы для безопасности)
        product_name = escape(item['product_name']) if item['product_name'] else "Товар"

        # Добавляем строку товара
        text += f"{i}. {status_emoji} <b>{product_name}</b>\n"

        # Полная ссылка (кликабельная)
        text += f"🔗 <a href=\"{escape(item['url'])}\">Открыть товар</a>\n"

        # Цена и дата обновления
        text += f"💰 {price_str}"
        if item['updated_at']:
            text += f" • 🕐 {item['updated_at'][:16]}"
        text += "\n\n"

    # Создаём inline-клавиатуру с кнопками удаления
    keyboard = get_items_list_keyboard(items)

    # Отправляем сообщение с HTML-разметкой
    await message.answer(
        text,
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@router.message(Command("history"))
async def cmd_history(message: types.Message):
    args = message.text.split()[1:]
    if not args:
        await message.answer(
            "📝 Отправьте ссылку на товар для просмотра истории:",
            reply_markup=get_cancel_keyboard()
        )
        return

    url = args[0].strip()
    await show_history(message, url)


async def show_history(message: types.Message, url: str):
    """Показать историю цен"""
    history = await get_price_history(url, limit=10)

    if not history:
        await message.answer("📭 Нет истории цен для этого товара.")
        return

    text = "📊 История цен:\n\n"
    for i, rec in enumerate(history):
        diff_str = ""
        if i > 0:
            prev = history[i - 1]['price']
            curr = rec['price']
            diff = curr - prev
            sign = "📈" if diff > 0 else "📉" if diff < 0 else "➡️"
            diff_str = f" {sign} {abs(diff):.2f}"
        text += f"• {rec['created_at'][:16]}: {rec['price']:.2f} BYN{diff_str}\n"

    await message.answer(text, reply_markup=get_back_keyboard())


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    """Справка"""
    await message.answer(
        "ℹ️ Помощь:\n\n"
        "1️⃣ Найдите товар на 1k.by / shop.by\n"
        "2️⃣ Скопируйте ссылку на страницу товара\n"
        "3️⃣ Нажмите «🔍 Отследить цену» и отправьте ссылку\n"
        "4️⃣ Бот будет проверять цену каждый час\n"
        "5️⃣ При изменении цены — вы получите уведомление!\n\n"
        "🗑 Управление товарами:\n"
        "• «📦 Мои товары» — просмотр и удаление\n"
        "• «📊 История цен» — график изменений\n\n"
        "🏠 В любое время нажмите «❌ Отмена» или /menu",
        reply_markup=get_main_keyboard()
    )


# --- ОБРАБОТЧИКИ ССЫЛОК (когда пользователь отправляет URL) ---

@router.message(F.text.startswith("http"))
async def handle_url(message: types.Message):
    """Обработка отправленной ссылки"""
    url = message.text.strip()

    if not await is_safe_url(url):
        await message.answer(
            f"❌ Недопустимая ссылка. Разрешены: {', '.join(ALLOWED_DOMAINS)}",
            reply_markup=get_main_keyboard()
        )
        return

    # Проверяем, есть ли такой товар уже
    items = await get_user_items(message.from_user.id)
    existing = any(item['url'] == url for item in items)

    if existing:
        await message.answer(
            "⚠️ Этот товар уже отслеживается!\n\n"
            "Выберите действие в меню:",
            reply_markup=get_main_keyboard()
        )
        return

    # Скачиваем страницу ОДИН РАЗ и используем для цены и названия
    html = await fetch_page(url)

    if not html:
        await message.answer(
            "❌ Не удалось загрузить страницу. Проверьте ссылку.",
            reply_markup=get_main_keyboard()
        )
        return

    # Получаем цену из уже скачанного html (без второго запроса)
    from parser import get_price, get_product_name
    from urllib.parse import urlparse
    from bs4 import BeautifulSoup

    domain = urlparse(url).netloc
    soup = BeautifulSoup(html, "html.parser")

    # --- Цена ---
    current_price = await get_price(url)

    if current_price is None:
        await message.answer(
            "❌ Не удалось получить цену. Проверьте ссылку.",
            reply_markup=get_main_keyboard()
        )
        return

    # --- Название: get_product_name принимает только url ---
    product_name = await get_product_name(url) or "Товар"
    # Сохраняем товар
    await add_item(message.from_user.id, url, product_name)
    await update_price(url, current_price)

    await message.answer(
        f"✅ Товар добавлен!\n\n"
        f"📦 {product_name}\n"
        f"🔗 {url[:50]}...\n"
        f"💰 Цена: {current_price:.2f} BYN\n"
        f"🔔 Уведомлю при изменении цены.",
        reply_markup=get_main_keyboard()
    )


# --- ОБРАБОТЧИКИ CALLBACK (КНОПКИ) ---


@router.callback_query(F.data == "my_refresh")
async def cb_refresh(callback: types.CallbackQuery):
    """Обновление списка товаров"""
    await callback.answer("🔄 Проверяю...")

    # Получаем товары
    items = await get_user_items(callback.from_user.id)

    if not items:
        await callback.answer("📭 У вас нет товаров", show_alert=True)
        return

    # Формируем текст
    text = "📦 <b>Ваши товары:</b>\n\n"

    for i, item in enumerate(items, 1):
        status_emoji = "🟢" if item['last_price'] else "🟡"
        price_str = f"{item['last_price']:.2f} BYN" if item['last_price'] else "???"
        product_name = escape(item['product_name']) if item['product_name'] else "Товар"

        text += f"{i}. {status_emoji} <b>{product_name}</b>\n"
        text += f"🔗 <a href=\"{escape(item['url'])}\">Открыть товар</a>\n"
        text += f"💰 {price_str}"
        if item['updated_at']:
            text += f" • 🕐 {item['updated_at'][:16]}"
        text += "\n\n"

    # Создаём клавиатуру
    keyboard = get_items_list_keyboard(items)

    # Пытаемся отредактировать сообщение
    try:
        await callback.message.edit_text(
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except TelegramBadRequest as e:
        # Если сообщение не изменилось — просто показываем уведомление
        if "message is not modified" in str(e):
            await callback.answer("✅ Список актуален!", show_alert=False)
        else:
            # Другие ошибки логируем
            raise e


@router.callback_query(F.data.startswith("del_"))
async def cb_delete(callback: types.CallbackQuery):
    """Удаление товара"""
    key = callback.data[4:]
    user_id = callback.from_user.id

    await callback.answer("⏳ Удаляю...")

    items = await get_user_items(user_id)
    url_to_delete = None

    for item in items:
        if make_callback_key(item['url']) == key:
            url_to_delete = item['url']
            break

    if not url_to_delete:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(
            "❌ Товар не найден.",
            reply_markup=get_main_keyboard()
        )
        return

    success = await delete_item(user_id, url_to_delete)

    if success:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(
            f"✅ Удалено:\n🔗 {url_to_delete[:50]}...",
            reply_markup=get_main_keyboard()
        )
    else:
        await callback.message.answer("❌ Ошибка при удалении.")


@router.callback_query(F.data.startswith("hist_"))
async def cb_history(callback: types.CallbackQuery):
    """Просмотр истории по кнопке"""
    key = callback.data[5:]
    user_id = callback.from_user.id

    await callback.answer("⏳ Загружаю историю...")

    items = await get_user_items(user_id)
    url = None

    for item in items:
        if make_callback_key(item['url']) == key:
            url = item['url']
            break

    if not url:
        await callback.answer("❌ Товар не найден.", show_alert=True)
        return

    await show_history(callback.message, url)


@router.callback_query(F.data == "back_menu")
async def cb_back_menu(callback: types.CallbackQuery):
    """Кнопка «Назад в меню»"""
    await callback.answer()
    await callback.message.answer(
        "🏠 Главное меню:",
        reply_markup=get_main_keyboard()
    )