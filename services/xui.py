"""
Сервис для работы с 3x-ui API.
Использует актуальный API (/panel/api/clients/*) с Bearer токеном.
"""

import asyncio
import uuid
from datetime import datetime
from typing import Optional
import logging

import httpx

from config import settings

logger = logging.getLogger(__name__)


class XUINode:
    """HTTP клиент для одного узла 3x-ui."""

    def __init__(
        self,
        host: str,
        token: str,
        inbound_id: int,
        node_name: str = "main",
    ):
        self.host = host.rstrip("/")
        self.token = token
        self.inbound_id = inbound_id
        self.node_name = node_name

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    async def _post(self, endpoint: str, json: dict) -> dict:
        url = f"{self.host}/{endpoint}"
        try:
            async with httpx.AsyncClient(verify=False, timeout=15) as http:
                resp = await http.post(url, headers=self._headers(), json=json)
                return resp.json()
        except Exception as e:
            logger.error(f"[{self.node_name}] POST {endpoint} error: {e}")
            return {"success": False, "msg": str(e)}

    async def _get(self, endpoint: str) -> dict:
        url = f"{self.host}/{endpoint}"
        try:
            async with httpx.AsyncClient(verify=False, timeout=15) as http:
                resp = await http.get(url, headers=self._headers())
                return resp.json()
        except Exception as e:
            logger.error(f"[{self.node_name}] GET {endpoint} error: {e}")
            return {"success": False, "msg": str(e)}

    async def login(self) -> bool:
        """Проверяем доступность API."""
        result = await self._get("panel/api/clients/list")
        return result.get("success", False)

    async def add_client(self, email: str, expires_at: datetime, limit_ip: int = 2) -> tuple[bool, str, str]:
        expires_ms = int(expires_at.timestamp() * 1000)
        result = await self._post("panel/api/clients/add", {
            "client": {
                "email": email,
                "expiryTime": expires_ms,
                "limitIp": limit_ip,
                "totalGB": 0,
                "enable": True,
            },
            "inboundIds": [self.inbound_id],
        })

        if result.get("success"):
            client_data = await self._get(f"panel/api/clients/get/{email}")
            if client_data.get("success"):
                obj = client_data.get("obj", {}).get("client", {})
                client_id = obj.get("uuid", "")
                sub_id = obj.get("subId", "")
                return True, client_id, sub_id
            return True, "", ""

        logger.error(f"[{self.node_name}] Add client failed: {result.get('msg')}")
        return False, "", ""

    async def update_client_expiry(self, client_id: str, email: str, expires_at: datetime) -> bool:
        expires_ms = int(expires_at.timestamp() * 1000)
        result = await self._post(f"panel/api/clients/update/{email}", {
            "email": email,
            "expiryTime": expires_ms,
            "enable": True,
        })
        return result.get("success", False)

    async def toggle_client(self, client_id: str, email: str, enable: bool) -> bool:
        result = await self._post(f"panel/api/clients/update/{email}", {
            "email": email,
            "enable": enable,
        })
        return result.get("success", False)

    async def delete_client(self, client_id: str, email: str) -> bool:
        result = await self._post(f"panel/api/clients/del/{email}", {})
        return result.get("success", False)

    async def get_client_link(self, client_id: str, email: str, sub_id: str = "") -> str | None:
        if sub_id:
            return f"https://leftvpn.online:2096/leftsubb/{sub_id}"
        return None

    async def is_healthy(self) -> bool:
        result = await self._get("panel/api/clients/list")
        return result.get("success", False)


class XUIManager:
    """
    Менеджер узлов 3x-ui.
    Для добавления нового узла вызови add_node() — всё остальное работает автоматически.
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

    async def create_client_all_nodes(self, email: str, expires_at: datetime) -> tuple[bool, str, str]:
        if not self._nodes:
            return False, "", ""

        ok, client_id, sub_id = await self.main_node.add_client(email, expires_at)
        if not ok:
            return False, "", ""

        extra = {k: v for k, v in self._nodes.items() if k != "main"}
        if extra:
            await asyncio.gather(
                *[n.add_client(email, expires_at) for n in extra.values()],
                return_exceptions=True,
            )

        return True, client_id, sub_id

    async def delete_client_all_nodes(self, client_id: str, email: str) -> bool:
        results = await asyncio.gather(
            *[n.delete_client(client_id, email) for n in self._nodes.values()],
            return_exceptions=True,
        )
        return any(r is True for r in results)

    async def toggle_client_all_nodes(self, client_id: str, email: str, enable: bool) -> bool:
        results = await asyncio.gather(
            *[n.toggle_client(client_id, email, enable) for n in self._nodes.values()],
            return_exceptions=True,
        )
        return any(r is True for r in results)

    async def update_expiry_all_nodes(self, client_id: str, email: str, expires_at: datetime) -> bool:
        results = await asyncio.gather(
            *[n.update_client_expiry(client_id, email, expires_at) for n in self._nodes.values()],
            return_exceptions=True,
        )
        return all(r is True for r in results)

    async def close_all(self):
        pass


# Глобальный менеджер
xui_manager = XUIManager()


def setup_xui():
    main_node = XUINode(
        host=settings.XUI_HOST,
        token=settings.XUI_TOKEN,
        inbound_id=settings.XUI_INBOUND_ID,
        node_name="main",
    )
    xui_manager.add_node("main", main_node)

    # ПРИМЕР добавления дополнительного узла:
    # node2 = XUINode(
    #     host="https://node2.example.com:2053/basepath",
    #     token="token_here",
    #     inbound_id=1,
    #     node_name="node2_de",
    # )
    # xui_manager.add_node("node2_de", node2)