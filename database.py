import aiosqlite
from typing import Optional, List

DB_NAME = "prices.db"


async def init_db():
    """Создание таблиц"""
    async with aiosqlite.connect(DB_NAME) as db:
        # Таблица отслеживаемых товаров
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tracked_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                url TEXT NOT NULL,
                product_name TEXT,
                last_price REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, url)
            )
        """)

        # Таблица истории цен (новое!)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                price REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()


async def add_item(user_id: int, url: str, product_name: str):
    """Добавить товар на отслеживание (без целевой цены)"""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            INSERT OR REPLACE INTO tracked_items 
            (user_id, url, product_name, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """, (user_id, url, product_name))
        await db.commit()


async def get_all_items() -> List[dict]:
    """Получить все товары для проверки цен"""
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM tracked_items")
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def update_price(url: str, price: float) -> bool:
    """
    Обновить цену товара.
    Возвращает True, если цена изменилась, False если осталась той же.
    """
    async with aiosqlite.connect(DB_NAME) as db:
        # Получаем последнюю цену
        cursor = await db.execute(
            "SELECT last_price FROM tracked_items WHERE url = ?",
            (url,)
        )
        row = await cursor.fetchone()

        if row is None:
            return False

        old_price = row[0]

        # Проверяем, изменилась ли цена (с погрешностью 0.01)
        if old_price is None or abs(old_price - price) > 0.01:
            # Обновляем текущую цену
            await db.execute("""
                UPDATE tracked_items 
                SET last_price = ?, updated_at = CURRENT_TIMESTAMP 
                WHERE url = ?
            """, (price, url))

            # Сохраняем в историю
            await db.execute("""
                INSERT INTO price_history (url, price) VALUES (?, ?)
            """, (url, price))

            await db.commit()
            return True  # Цена изменилась

        await db.commit()
        return False  # Цена не изменилась


async def get_price_history(url: str, limit: int = 5) -> List[dict]:
    """Получить историю цен для товара"""
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM price_history WHERE url = ? ORDER BY created_at DESC LIMIT ?",
            (url, limit)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_user_items(user_id: int) -> List[dict]:
    """Получить товары конкретного пользователя"""
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM tracked_items WHERE user_id = ?",
            (user_id,)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def get_item_by_url(url: str) -> Optional[dict]:
    """Получить товар по URL (для проверки перед удалением)"""
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM tracked_items WHERE url = ?",
            (url,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def delete_item(user_id: int, url: str) -> bool:
    """
    Удалить товар из отслеживания.
    Возвращает True, если удаление прошло успешно.
    """
    async with aiosqlite.connect(DB_NAME) as db:
        # Сначала проверяем, что товар существует и принадлежит пользователю
        cursor = await db.execute(
            "SELECT id FROM tracked_items WHERE user_id = ? AND url = ?",
            (user_id, url)
        )
        row = await cursor.fetchone()

        if row is None:
            return False  # Товар не найден или не принадлежит пользователю

        # Удаляем из основной таблицы
        await db.execute(
            "DELETE FROM tracked_items WHERE user_id = ? AND url = ?",
            (user_id, url)
        )
        # Удаляем историю цен
        await db.execute(
            "DELETE FROM price_history WHERE url = ?",
            (url,)
        )
        await db.commit()
        return True