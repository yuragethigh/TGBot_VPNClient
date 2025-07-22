from aiogram import Dispatcher
from app.handlers import start, payments


def register_handlers(dp: Dispatcher):
    dp.include_router(start.router)
    dp.include_router(payments.router)
