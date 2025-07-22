import uuid
from typing import Any, Dict

import aiohttp
import ssl
import certifi

from app.config import Config

YK_API_URL = "https://api.yookassa.ru/v3/payments"
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


async def create_payment(amount: int, description: str, return_url: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
    headers = {
        "Content-Type": "application/json",
        "Idempotence-Key": str(uuid.uuid4()),
    }
    auth = aiohttp.BasicAuth(login=Config.YK_SHOP_ID, password=Config.YK_SECRET_KEY)
    payload = {
        "amount": {"value": f"{amount}.00", "currency": "RUB"},
        "capture": True,
        "confirmation": {"type": "redirect", "return_url": return_url},
        "description": description,
        "metadata": metadata,
    }

    async with aiohttp.ClientSession(auth=auth) as session:
        async with session.post(YK_API_URL, headers=headers, json=payload, ssl=SSL_CONTEXT) as resp:
            data = await resp.json()
            if resp.status >= 300:
                raise RuntimeError(f"YooKassa error {resp.status}: {data}")
            return data


async def get_payment(payment_id: str) -> Dict[str, Any]:
    auth = aiohttp.BasicAuth(login=Config.YK_SHOP_ID, password=Config.YK_SECRET_KEY)
    async with aiohttp.ClientSession(auth=auth) as session:
        async with session.get(f"{YK_API_URL}/{payment_id}", ssl=SSL_CONTEXT) as resp:
            data = await resp.json()
            if resp.status >= 300:
                raise RuntimeError(f"YooKassa status error {resp.status}: {data}")
            return data
