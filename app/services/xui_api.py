import json
import ssl
from typing import Optional
from urllib.parse import urljoin, quote, urlencode

import aiohttp

from app.config import Config


class XUIClient:
    def __init__(self, base_url: str, username: str, password: str, inbound_id: int, ignore_ssl: bool = True):
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

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(ssl=self._ssl),
                cookie_jar=aiohttp.CookieJar(unsafe=True),
                headers={"Accept": "application/json, text/plain, */*"},
            )
        return self._session

    async def _request(self, method: str, path: str, *, data=None, retry: int = 1):
        s = await self._get_session()
        url = urljoin(self.base_url + "/", path.lstrip("/"))

        resp = await s.request(method, url, data=data, allow_redirects=False)
        try:
            # редирект == слетела сессия
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

    async def ensure_login(self):
        if self._logged_in:
            return
        payload = {"username": self.username, "password": self.password}
        data = await self._request("POST", "login", data=payload, retry=0)
        if not data.get("success"):
            raise RuntimeError(f"3x-ui login failed: {data.get('msg')}")
        self._logged_in = True
        print("[XUI] logged in")

    async def add_client(self, uuid_str: str, email: str, expiry_ms: int, limit_gb: int = 0) -> str:
        client_obj = {
            "id": uuid_str,
            "flow": "xtls-rprx-vision",
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

        # если панель вернула ссылку — используем её
        obj = data.get("obj") or {}
        if isinstance(obj, dict) and obj.get("links"):
            link = obj["links"][0]
            print(f"[XUI] client added (obj link): {email}")
            return link

        # иначе генерим сами, ЖЁСТКО по константам
        link = self._build_vless_link(uuid_str, email)
        print(f"[XUI] client added (hardcoded link): {email}")
        return link

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
