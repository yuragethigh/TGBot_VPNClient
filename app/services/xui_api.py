from __future__ import annotations

import json
import ssl
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List
from urllib.parse import urljoin

import aiohttp

from app.config import Config


class XUIClient:
    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        inbound_id: int,
        ignore_ssl: bool = True
    ) -> None:
        if not base_url:
            raise ValueError("XUI base_url is empty")

        self.base_url = base_url.rstrip("/")
        if not self.base_url.startswith(("http://", "https://")):
            self.base_url = "http://" + self.base_url

        self.username = username
        self.password = password
        self.inbound_id = inbound_id

        self._session: Optional[aiohttp.ClientSession] = None
        self._logged_in = False
        self._ssl = False if ignore_ssl else ssl.create_default_context()

    # -------------------- low-level http --------------------
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(ssl=self._ssl),
                cookie_jar=aiohttp.CookieJar(unsafe=True),
                headers={"Accept": "application/json, text/plain, */*"},
            )
        return self._session

    async def _request(self, method: str, path: str, *, data=None, retry: int = 1) -> Dict:
        s = await self._get_session()
        url = urljoin(self.base_url + "/", path.lstrip("/"))

        resp = await s.request(method, url, data=data, allow_redirects=False)
        try:
            if resp.status in (301, 302, 303, 307, 308):
                if retry > 0:
                    self._logged_in = False
                    await self.ensure_login()
                    return await self._request(method, path, data=data, retry=retry - 1)
                raise RuntimeError(f"Too many redirects to {resp.headers.get('Location')}")

            text = await resp.text()
            try:
                js = json.loads(text or "{}")
            except json.JSONDecodeError:
                js = {}

            if (not js.get("success", True)) and "session has expired" in str(js.get("msg", "")).lower():
                if retry > 0:
                    self._logged_in = False
                    await self.ensure_login()
                    return await self._request(method, path, data=data, retry=retry - 1)
                raise RuntimeError(f"Session expired and retry failed: {js}")

            return js
        finally:
            resp.release()

    async def ensure_login(self) -> None:
        if self._logged_in:
            return
        payload = {"username": self.username, "password": self.password}
        data = await self._request("POST", "login", data=payload, retry=0)
        if not data.get("success"):
            raise RuntimeError(f"3x-ui login failed: {data.get('msg')}")
        self._logged_in = True
        print("[XUI] logged in")

    # -------------------- helpers --------------------
    async def _get_inbound_settings(self) -> Dict:
        data = await self._request("GET", f"panel/api/inbounds/get/{self.inbound_id}")
        if not data.get("success"):
            raise RuntimeError(f"get inbound error: {data.get('msg')}")
        raw = data["obj"]["settings"]
        return json.loads(raw or "{}")

    async def find_client_by_email(self, email: str) -> Optional[Dict]:
        settings = await self._get_inbound_settings()
        for c in settings.get("clients", []):
            if c.get("email") == email:
                return c
        return None

    async def _update_single_client(self, client: Dict) -> None:
    
        payload = {
            "id": self.inbound_id,
            "settings": json.dumps({"clients": [client]}),
        }

        # сначала пробуем путь с uuid
        path = f"panel/api/inbounds/updateClient/{client['id']}"
        data = await self._request("POST", path, data=payload)
        if data.get("success"):
            return

        # fallback: старые форки
        alt = await self._request("POST", "panel/api/inbounds/updateClient", data=payload)
        if not alt.get("success"):
            raise RuntimeError(f"updateClient error: {data.get('msg')} / {alt.get('msg')}")

    # -------------------- public API --------------------
    async def add_client(self, uuid_str: str, email: str, expiry_ms: int, limit_gb: int = 0) -> str:
        await self.ensure_login()

        client_obj = {
            "id": uuid_str,
            "flow": Config.VLESS_FLOW,
            "email": email,
            "enable": True,
            "limitIp": 0,
            "totalGB": limit_gb,
            "expiryTime": expiry_ms,
            "tgId": "",
            "subId": "",
            "reset": 0,
        }

        payload = {
            "id": self.inbound_id,
            "settings": json.dumps({"clients": [client_obj]}),
        }

        data = await self._request("POST", "panel/api/inbounds/addClient", data=payload, retry=2)
        if not data.get("success"):
            raise RuntimeError(f"addClient error: {data.get('msg')}")
        print(f"[XUI] client added: {email}")
        return self._build_vless_link(uuid_str, email)

    async def extend_client(self, email: str, add_days: int, limit_gb: int = 0) -> str:
        await self.ensure_login()

        now_ms = int(time.time() * 1000)
        add_ms = add_days * 24 * 60 * 60 * 1000

        settings = await self._get_inbound_settings()
        clients: List[Dict] = settings.get("clients", [])

        for c in clients:
            if c.get("email") == email:
                base = max(c.get("expiryTime", 0), now_ms)
                c["expiryTime"] = base + add_ms
                if limit_gb:
                    c["totalGB"] = limit_gb
                await self._update_single_client(c)
                print(f"[XUI] client extended: {email}, new expiry={c['expiryTime']}")
                return self._build_vless_link(c["id"], email)

        raise RuntimeError("extend_client: client not found")

    async def upsert_client(self, tg_user_id: int, days: int, limit_gb: int = 0) -> str:
        await self.ensure_login()

        email = f"user_{tg_user_id}@bot"
        existing = await self.find_client_by_email(email)
        if existing:
            return await self.extend_client(email=email, add_days=days, limit_gb=limit_gb)

        uid = str(uuid.uuid4())
        expiry_ms = int((datetime.now(tz=timezone.utc) + timedelta(days=days)).timestamp() * 1000)
        return await self.add_client(uuid_str=uid, email=email, expiry_ms=expiry_ms, limit_gb=limit_gb)

    def _build_vless_link(self, uuid_str: str, email: str) -> str:
        tag = f"{Config.LINK_TAG_PREFIX}-{email}".replace("@", "%40")
        base = (
            f"vless://{uuid_str}@{Config.LINK_HOST}:{Config.LINK_PORT}/?"
            f"type=tcp"
            f"&security=reality"
            f"&pbk={Config.VLESS_PBK}"
            f"&fp={Config.VLESS_FP}"
            f"&sni={Config.VLESS_SNI}"
            f"&sid={Config.VLESS_SID}"
            f"&spx={Config.VLESS_SPX}"
            f"&flow={Config.VLESS_FLOW}"
        )
        return f"{base}#{tag}"

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
            self._logged_in = False
