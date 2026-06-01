"""
Сервис для работы с 3x-ui API через библиотеку py3xui.

Архитектура поддерживает несколько узлов (nodes):
- Каждый XUIClient работает с одним сервером
- XUIManager управляет всеми узлами
- При добавлении нового узла достаточно добавить его данные в БД/конфиг
  и создать новый XUIClient — весь остальной код менять не нужно.
"""

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Optional
import logging

from py3xui import AsyncApi
from py3xui.client.client import Client

from config import settings

logger = logging.getLogger(__name__)


class XUINode:
    """Обёртка над AsyncApi для одного узла."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        token: str,
        inbound_id: int,
        node_name: str = "main",
    ):
        self.host = host
        self.inbound_id = inbound_id
        self.node_name = node_name
        self.api = AsyncApi(
            host=host,
            username=username,
            password=password,
            token=token,
            logger=logging.getLogger(f"xui_{node_name}"),
        )

    async def login(self) -> bool:
        try:
            await self.api.login()
            return True
        except Exception as e:
            logger.error(f"[{self.node_name}] Login error: {e}")
            return False

    async def add_client(self, email: str, expires_at: datetime, limit_ip: int = 1) -> tuple[bool, str]:
        client_id = str(uuid.uuid4())
        expires_ms = int(expires_at.timestamp() * 1000)

        client = Client(
            id=client_id,
            email=email,
            limit_ip=limit_ip,
            total_gb=0,
            expiry_time=expires_ms,
            enable=True,
            flow="",
        )

        try:
            await self.api.client.add(self.inbound_id, [client])
            return True, client_id
        except Exception as e:
            logger.error(f"[{self.node_name}] Add client error: {e}")
            return False, ""

    async def update_client_expiry(self, client_id: str, email: str, expires_at: datetime) -> bool:
        expires_ms = int(expires_at.timestamp() * 1000)
        client = Client(
            id=client_id,
            email=email,
            expiry_time=expires_ms,
            enable=True,
            flow="",
        )
        try:
            await self.api.client.update(client_id, client)
            return True
        except Exception as e:
            logger.error(f"[{self.node_name}] Update client error: {e}")
            return False

    async def toggle_client(self, client_id: str, email: str, enable: bool) -> bool:
        client = Client(
            id=client_id,
            email=email,
            enable=enable,
            flow="",
        )
        try:
            await self.api.client.update(client_id, client)
            return True
        except Exception as e:
            logger.error(f"[{self.node_name}] Toggle client error: {e}")
            return False

    async def delete_client(self, client_id: str) -> bool:
        try:
            await self.api.client.delete(self.inbound_id, client_id)
            return True
        except Exception as e:
            logger.error(f"[{self.node_name}] Delete client error: {e}")
            return False

    async def get_client_link(self, client_id: str, email: str) -> str | None:
        """Сформировать vless:// ссылку из настроек inbound."""
        try:
            inbounds = await self.api.inbound.get_list()
            inbound = next((i for i in inbounds if i.id == self.inbound_id), None)
            if not inbound:
                return None

            import json
            from urllib.parse import urlparse

            stream = inbound.stream_settings
            if isinstance(stream, str):
                stream = json.loads(stream)

            network = stream.get("network", "ws")
            security = stream.get("security", "tls")
            ws_settings = stream.get("wsSettings", {})
            path = ws_settings.get("path", "/")
            host_header = ws_settings.get("headers", {}).get("Host", "")
            tls_settings = stream.get("tlsSettings", {})
            server_name = tls_settings.get("serverName", "")

            parsed = urlparse(self.host)
            server_host = parsed.hostname
            port = inbound.port

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

    async def is_healthy(self) -> bool:
        try:
            await self.api.inbound.get_list()
            return True
        except Exception:
            return False


class XUIManager:
    """
    Менеджер узлов 3x-ui.

    Сейчас работает с одним главным узлом.
    Для добавления новых узлов достаточно вызвать add_node() —
    все методы работы с клиентами автоматически применяются ко всем узлам.
    """

    def __init__(self):
        self._nodes: dict[str, XUINode] = {}

    def add_node(self, name: str, node: XUINode):
        self._nodes[name] = node

    @property
    def main_node(self) -> XUINode:
        return self._nodes["main"]

    async def init_all(self):
        tasks = [node.login() for node in self._nodes.values()]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for name, result in zip(self._nodes.keys(), results):
            if result is True:
                logger.info(f"XUI node '{name}' connected")
            else:
                logger.error(f"XUI node '{name}' connection FAILED: {result}")

    async def create_client_all_nodes(self, email: str, expires_at: datetime) -> tuple[bool, str]:
        if not self._nodes:
            return False, ""

        ok, client_id = await self.main_node.add_client(email, expires_at)
        if not ok:
            return False, ""

        extra = {k: v for k, v in self._nodes.items() if k != "main"}
        if extra:
            await asyncio.gather(*[n.add_client(email, expires_at) for n in extra.values()], return_exceptions=True)

        return True, client_id

    async def delete_client_all_nodes(self, client_id: str) -> bool:
        results = await asyncio.gather(
            *[n.delete_client(client_id) for n in self._nodes.values()], return_exceptions=True
        )
        return any(r is True for r in results)

    async def toggle_client_all_nodes(self, client_id: str, email: str, enable: bool) -> bool:
        results = await asyncio.gather(
            *[n.toggle_client(client_id, email, enable) for n in self._nodes.values()], return_exceptions=True
        )
        return any(r is True for r in results)

    async def update_expiry_all_nodes(self, client_id: str, email: str, expires_at: datetime) -> bool:
        results = await asyncio.gather(
            *[n.update_client_expiry(client_id, email, expires_at) for n in self._nodes.values()], return_exceptions=True
        )
        return all(r is True for r in results)

    async def close_all(self):
        pass  # py3xui не требует явного закрытия


# Глобальный менеджер
xui_manager = XUIManager()


def setup_xui():
    main_node = XUINode(
        host=settings.XUI_HOST,
        username=settings.XUI_USERNAME,
        password=settings.XUI_PASSWORD,
        token=settings.XUI_TOKEN,
        inbound_id=settings.XUI_INBOUND_ID,
        node_name="main",
    )
    xui_manager.add_node("main", main_node)

    # ПРИМЕР добавления дополнительного узла (раскомментировать когда появится):
    # node2 = XUINode(
    #     host="https://node2.example.com:2053",
    #     username="admin",
    #     password="password",
    #     token="token_here",
    #     inbound_id=1,
    #     node_name="node2_de",
    # )
    # xui_manager.add_node("node2_de", node2)