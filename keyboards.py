from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton


# --- Главное меню (Reply Keyboard) ---
def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Основное меню с кнопками команд"""
    keyboard = [
        [
            KeyboardButton(text="🔍 Отследить цену"),
            KeyboardButton(text="📦 Мои товары")
        ],
        [
            KeyboardButton(text="📊 История цен"),
            KeyboardButton(text="❓ Помощь")
        ],
        [
            KeyboardButton(text="🔔 Настройки уведомлений")
        ]
    ]
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,  # Автоматически подстраивает размер
        one_time_keyboard=False  # Не скрывать после нажатия
    )


def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура с кнопкой отмены (для режима ввода)"""
    keyboard = [
        [KeyboardButton(text="❌ Отмена")]
    ]
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=True
    )


def get_empty_keyboard() -> ReplyKeyboardMarkup:
    """Пустая клавиатура (скрывает кнопки)"""
    return ReplyKeyboardMarkup(
        keyboard=[],
        resize_keyboard=True
    )


# --- Inline кнопки для товаров ---
def get_delete_inline_keyboard(url: str) -> InlineKeyboardMarkup:
    """Кнопка удаления для конкретного товара"""
    import hashlib
    key = hashlib.md5(url.encode('utf-8')).hexdigest()[:8]

    keyboard = [
        [
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"del_{key}"),
            InlineKeyboardButton(text="📊 История", callback_data=f"hist_{key}")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_items_list_keyboard(items: list) -> InlineKeyboardMarkup:
    """Клавиатура со списком товаров (для /my)"""
    import hashlib
    keyboard = []

    for item in items:
        key = hashlib.md5(item['url'].encode('utf-8')).hexdigest()[:8]

        name = item.get('product_name') or 'Товар'
        short_name = (name[:25] + '…') if len(name) > 25 else name

        keyboard.append([
            InlineKeyboardButton(
                text=f"🗑 {short_name}",
                callback_data=f"del_{key}"
            ),
            InlineKeyboardButton(
                text="📊 История",
                callback_data=f"hist_{key}"
            )
        ])

    keyboard.append([
        InlineKeyboardButton(text="🔄 Обновить", callback_data="my_refresh")
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_back_keyboard() -> InlineKeyboardMarkup:
    """Кнопка «Назад в меню»"""
    keyboard = [
        [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)