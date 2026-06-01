"""
Сервис для работы с 3x-ui API.

Архитектура поддерживает несколько узлов (nodes):
- Каждый XUIClient работает с одним сервером
- XUIManager управляет всеми узлами
- При добавлении нового узла достаточно добавить его данные в БД/конфиг
  и создать новый XUIClient — весь остальной код менять не нужно.
"""

import asyncio
import aiohttp
import uuid
from datetime import datetime, timezone
from typing import Optional
import logging

from config import settings

logger = logging.getLogger(__name__)


class XUIClient:
    """Клиент для одного экземпляра 3x-ui."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        inbound_id: int,
        node_name: str = "main",
    ):
        self.host = host.rstrip("/")
        self.username = username
        self.password = password
        self.inbound_id = inbound_id
        self.node_name = node_name
        self._session: Optional[aiohttp.ClientSession] = None
        self._cookies: Optional[aiohttp.CookieJar] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._cookies = aiohttp.CookieJar()
            self._session = aiohttp.ClientSession(
                cookie_jar=self._cookies,
                connector=aiohttp.TCPConnector(ssl=False),  # Установить True если есть валидный TLS
            )
        return self._session

    async def login(self) -> bool:
        session = await self._get_session()
        try:
            async with session.post(
                f"{self.host}",
                json={"username": self.username, "password": self.password},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
                return data.get("success", False)
        except Exception as e:
            logger.error(f"[{self.node_name}] Login error: {e}")
            return False

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        """Выполнить запрос, при необходимости повторно залогиниться."""
        session = await self._get_session()
        url = f"{self.host}{path}"
        try:
            async with session.request(
                method, url, timeout=aiohttp.ClientTimeout(total=15), **kwargs
            ) as resp:
                if resp.status == 401:
                    # Сессия истекла — перелогиниться
                    await self.login()
                    async with session.request(
                        method, url, timeout=aiohttp.ClientTimeout(total=15), **kwargs
                    ) as resp2:
                        return await resp2.json()
                return await resp.json()
        except Exception as e:
            logger.error(f"[{self.node_name}] Request error {method} {path}: {e}")
            return {"success": False, "msg": str(e)}

    # -------------------------------------------------------------------------
    # Клиенты
    # -------------------------------------------------------------------------

    def _build_client_payload(
        self,
        client_id: str,
        email: str,
        expires_ms: int,
        limit_ip: int = 1,
    ) -> dict:
        return {
            "id": client_id,
            "alterId": 0,
            "email": email,
            "limitIp": limit_ip,
            "totalGB": 0,
            "expiryTime": expires_ms,
            "enable": True,
            "tgId": "",
            "subId": "",
            "reset": 0,
        }

    async def add_client(
        self,
        email: str,
        expires_at: datetime,
        limit_ip: int = 1,
    ) -> tuple[bool, str]:
        """
        Создать клиента в 3x-ui.
        Возвращает (success, client_id).
        """
        client_id = str(uuid.uuid4())
        expires_ms = int(expires_at.timestamp() * 1000)

        payload = {
            "id": self.inbound_id,
            "settings": {
                "clients": [self._build_client_payload(client_id, email, expires_ms, limit_ip)]
            },
        }

        result = await self._request("POST", "/panel/api/inbounds/addClient", json=payload)
        if result.get("success"):
            return True, client_id
        logger.error(f"[{self.node_name}] Add client failed: {result.get('msg')}")
        return False, ""

    async def update_client_expiry(
        self,
        client_id: str,
        email: str,
        expires_at: datetime,
    ) -> bool:
        """Обновить срок действия клиента."""
        expires_ms = int(expires_at.timestamp() * 1000)
        payload = {
            "id": self.inbound_id,
            "settings": {
                "clients": [self._build_client_payload(client_id, email, expires_ms)]
            },
        }
        result = await self._request(
            "POST", f"/panel/api/inbounds/updateClient/{client_id}", json=payload
        )
        return result.get("success", False)

    async def toggle_client(self, client_id: str, email: str, enable: bool) -> bool:
        """Включить/выключить клиента."""
        # Сначала получаем текущие данные клиента
        inbound = await self.get_inbound()
        if not inbound:
            return False

        clients = inbound.get("clientStats", [])
        client_data = None
        for c in inbound.get("settings", {}).get("clients", []):
            if c.get("id") == client_id:
                client_data = c
                break

        if not client_data:
            return False

        client_data["enable"] = enable
        payload = {
            "id": self.inbound_id,
            "settings": {"clients": [client_data]},
        }
        result = await self._request(
            "POST", f"/panel/api/inbounds/updateClient/{client_id}", json=payload
        )
        return result.get("success", False)

    async def delete_client(self, client_id: str) -> bool:
        """Удалить клиента из inbound."""
        result = await self._request(
            "POST", f"/panel/api/inbounds/{self.inbound_id}/delClient/{client_id}"
        )
        return result.get("success", False)

    async def get_client_link(self, client_id: str, email: str) -> str | None:
        """
        Сформировать ссылку vless:// для подключения.
        Получаем настройки inbound и собираем URI вручную.
        """
        inbound = await self.get_inbound()
        if not inbound:
            return None

        # Парсим настройки
        import json
        try:
            settings_raw = inbound.get("streamSettings", "{}")
            if isinstance(settings_raw, str):
                stream = json.loads(settings_raw)
            else:
                stream = settings_raw

            network = stream.get("network", "ws")
            security = stream.get("security", "tls")

            ws_settings = stream.get("wsSettings", {})
            path = ws_settings.get("path", "/")
            host_header = ws_settings.get("headers", {}).get("Host", "")

            tls_settings = stream.get("tlsSettings", {})
            server_name = tls_settings.get("serverName", "")

            # Получаем хост из URL панели
            from urllib.parse import urlparse
            parsed = urlparse(self.host)
            server_host = parsed.hostname
            port = inbound.get("port", 443)

            link = (
                f"vless://{client_id}@{server_host}:{port}"
                f"?type={network}"
                f"&security={security}"
                f"&path={path}"
                f"&host={host_header or server_name}"
                f"&sni={server_name}"
                f"#{email}"
            )
            return link
        except Exception as e:
            logger.error(f"[{self.node_name}] Build link error: {e}")
            return None

    async def get_inbound(self) -> dict | None:
        result = await self._request("GET", f"/panel/api/inbounds/get/{self.inbound_id}")
        if result.get("success"):
            return result.get("obj")
        return None

    async def is_healthy(self) -> bool:
        """Проверить доступность узла."""
        try:
            result = await self._request("GET", "/panel/api/inbounds/list")
            return result.get("success", False)
        except Exception:
            return False

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()


class XUIManager:
    """
    Менеджер узлов 3x-ui.

    Сейчас работает с одним главным узлом.
    Для добавления новых узлов достаточно вызвать add_node() —
    все методы работы с клиентами автоматически применяются ко всем узлам.
    """

    def __init__(self):
        self._nodes: dict[str, XUIClient] = {}

    def add_node(self, name: str, client: XUIClient):
        self._nodes[name] = client

    def get_node(self, name: str) -> XUIClient | None:
        return self._nodes.get(name)

    @property
    def main_node(self) -> XUIClient:
        return self._nodes["main"]

    async def init_all(self):
        """Залогиниться на всех узлах."""
        tasks = [node.login() for node in self._nodes.values()]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for name, result in zip(self._nodes.keys(), results):
            if result is True:
                logger.info(f"XUI node '{name}' connected")
            else:
                logger.error(f"XUI node '{name}' connection FAILED: {result}")

    async def create_client_all_nodes(
        self,
        email: str,
        expires_at: datetime,
    ) -> tuple[bool, str]:
        """
        Создать клиента на всех узлах (один email, один client_id).
        Возвращает (success, client_id).

        При наличии нескольких узлов клиент создаётся с одинаковым ID на всех,
        что позволяет использовать один конфиг для подключения к любому узлу.
        """
        if not self._nodes:
            return False, ""

        # Генерируем единый client_id
        client_id = str(uuid.uuid4())

        main = self.main_node
        # Сначала создаём на главном
        success, created_id = await main.add_client(email, expires_at)
        if not success:
            return False, ""

        # На дополнительных узлах создаём с тем же ID (если они есть)
        extra_nodes = {k: v for k, v in self._nodes.items() if k != "main"}
        if extra_nodes:
            tasks = []
            for node in extra_nodes.values():
                tasks.append(node.add_client(email, expires_at))
            await asyncio.gather(*tasks, return_exceptions=True)

        return True, created_id

    async def delete_client_all_nodes(self, client_id: str) -> bool:
        tasks = [node.delete_client(client_id) for node in self._nodes.values()]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return any(r is True for r in results)

    async def toggle_client_all_nodes(self, client_id: str, email: str, enable: bool) -> bool:
        tasks = [node.toggle_client(client_id, email, enable) for node in self._nodes.values()]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return any(r is True for r in results)

    async def update_expiry_all_nodes(self, client_id: str, email: str, expires_at: datetime) -> bool:
        tasks = [node.update_client_expiry(client_id, email, expires_at) for node in self._nodes.values()]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return all(r is True for r in results)

    async def close_all(self):
        for node in self._nodes.values():
            await node.close()


# Глобальный менеджер
xui_manager = XUIManager()


def setup_xui():
    """Инициализировать XUI из настроек."""
    main_client = XUIClient(
        host=settings.XUI_HOST,
        username=settings.XUI_USERNAME,
        password=settings.XUI_PASSWORD,
        inbound_id=settings.XUI_INBOUND_ID,
        node_name="main",
    )
    xui_manager.add_node("main", main_client)

    # ПРИМЕР добавления дополнительного узла (раскомментировать когда появится):
    # node2 = XUIClient(
    #     host="https://node2.example.com:2053",
    #     username="admin",
    #     password="password",
    #     inbound_id=1,
    #     node_name="node2_de",
    # )
    # xui_manager.add_node("node2_de", node2)
