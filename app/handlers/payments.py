#payments.py
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from aiogram import Router, F
from aiogram.types import CallbackQuery

from app.config import Config
from app.services.yookassa_api import create_payment, get_payment
from app.services.xui_api import XUIClient

router = Router()
PAYMENTS: dict[str, dict] = {}
_xui_client: XUIClient | None = None


def get_xui_client() -> XUIClient:
    global _xui_client
    if _xui_client is None:
        _xui_client = XUIClient(
            base_url=Config.XUI_URL,
            username=Config.XUI_USERNAME,
            password=Config.XUI_PASSWORD,
            inbound_id=Config.XUI_INBOUND_ID,
            ignore_ssl=Config.XUI_IGNORE_SSL,
        )
    return _xui_client


@router.callback_query(F.data.startswith("pay:"))
async def handle_pay(cb: CallbackQuery):
    plan_code = cb.data.split(":", 1)[1]
    if plan_code == "month":
        amount, days = Config.PLAN_MONTH_PRICE, Config.PLAN_MONTH_DAYS
    else:
        amount, days = Config.PLAN_3MONTH_PRICE, Config.PLAN_3MONTH_DAYS

    payment = await create_payment(
        amount=amount,
        description=f"Оплата тарифа {plan_code} для user {cb.from_user.id}",
        return_url=Config.YK_RETURN_URL,
        metadata={"tg_user_id": cb.from_user.id, "plan": plan_code, "days": days},
    )

    url = payment.get("confirmation", {}).get("confirmation_url")
    if not url:
        await cb.message.answer(f"Ошибка создания платежа:\n<code>{payment}</code>")
        await cb.answer()
        return

    msg = await cb.message.edit_text(
        f"Ссылка на оплату: <a href=\"{url}\">Оплатить</a>\n\n"
        "После оплаты я проверю статус и пришлю доступ.",
        disable_web_page_preview=True,
    )
    await cb.answer()

    pid = payment["id"]
    PAYMENTS[pid] = {
        "user_id": cb.from_user.id,
        "days": days,
        "msg_id": msg.message_id,
        "chat_id": msg.chat.id,
    }

    asyncio.create_task(_watch_payment(cb.bot, pid))


async def _watch_payment(bot, payment_id: str):
    info = PAYMENTS[payment_id]
    user_id, days = info["user_id"], info["days"]
    deadline = datetime.now(tz=timezone.utc) + timedelta(minutes=10)

    try:
        while datetime.now(tz=timezone.utc) < deadline:
            data = await get_payment(payment_id)
            status, paid = data.get("status"), data.get("paid")
            print(f"[YK] payment {payment_id}: status={status}, paid={paid}")

            if paid or status == "succeeded":
                asyncio.create_task(_after_success_payment(bot, user_id, days, info))
                return

            if status in ("canceled", "expired", "refunded"):
                await bot.send_message(user_id, "Платёж отменён/истёк. Попробуйте ещё раз /start")
                return

            await asyncio.sleep(5)

        await bot.send_message(user_id, "Не дождался подтверждения оплаты. Если вы оплатили — напишите в поддержку.")
    except Exception as e:
        await bot.send_message(user_id, f"Ошибка при обработке оплаты: <code>{e}</code>")
        raise


async def _after_success_payment(bot, user_id: int, days: int, info: dict | None):
    try:
        print("[FLOW] after_success start")
        xui = get_xui_client()

        # ВАЖНО: никакого add_client напрямую
        link = await xui.upsert_client(tg_user_id=user_id, days=days, limit_gb=0)

        if info:
            try:
                await bot.edit_message_text(
                    chat_id=info["chat_id"],
                    message_id=info["msg_id"],
                    text="✅ Оплата подтверждена. Доступ отправлен отдельным сообщением.",
                )
            except Exception:
                pass

        await bot.send_message(user_id, f"✅ Оплата получена.\nВаша ссылка:\n<code>{link}</code>")
        print("[FLOW] after_success done")
    except Exception as e:
        await bot.send_message(user_id, f"Ошибка выдачи доступа: <code>{e}</code>")
        raise
