from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message):
    kb = InlineKeyboardBuilder()
    kb.button(text="ДАЛЕЕ ➜", callback_data="go_next")
    await message.answer("Добро пожаловать!", reply_markup=kb.as_markup())


@router.callback_query(F.data == "go_next")
async def show_plans(cb: CallbackQuery):
    kb = InlineKeyboardBuilder()
    kb.button(text="399 ₽ / 1 месяц", callback_data="pay:month")
    kb.button(text="1000 ₽ / 3 месяца", callback_data="pay:3month")
    kb.adjust(1)
    await cb.message.edit_text("Выберите тариф:", reply_markup=kb.as_markup())
    await cb.answer()
