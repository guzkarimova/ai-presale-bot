import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import settings
from database.database import init_db
from handlers.interview import router as interview_router
from handlers.start import router as start_router
from services.presale_pipeline import recover_pending_presale_tasks


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


async def main() -> None:
    if not settings.telegram_bot_token:
        logging.critical("TELEGRAM_BOT_TOKEN is not set. Fill .env before running the bot.")
        raise SystemExit(1)

    init_db()

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(start_router)
    dp.include_router(interview_router)

    logging.info("Bot is starting")
    await bot.delete_webhook(drop_pending_updates=True)
    await recover_pending_presale_tasks(bot)
    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
