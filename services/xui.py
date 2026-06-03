"""
Сервис для работы с 3x-ui API.
Использует актуальный API (/panel/api/clients/*) с Bearer токеном.
Поддержка multiple inboundIds.
"""

import asyncio
from datetime import datetime
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
        node_name: str = "main",
    ):
        self.host = host.rstrip("/")
        self.token = token
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
        result = await self._get("panel/api/clients/list")
        return result.get("success", False)

    async def add_client(
        self,
        email: str,
        expires_at: datetime,
        inbound_ids: list[int],
        limit_ip: int = 2,
        total_gb: int = 0,
    ) -> tuple[bool, str, str]:

        expires_ms = int(expires_at.timestamp() * 1000)

        result = await self._post("panel/api/clients/add", {
        "client": {
            "email": email,
            "expiryTime": expires_ms,
            "limitIp": limit_ip,
            "totalGB": total_gb * 1024 * 1024 * 1024,
            "tgId": 0,
            "enable": True,
        },
        "inboundIds": inbound_ids,
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

    async def update_client_expiry(
        self,
        client_id: str,
        email: str,
        expires_at: datetime,
    ) -> bool:

        expires_ms = int(expires_at.timestamp() * 1000)

        result = await self._post(f"panel/api/clients/update/{email}", {
            "email": email,
            "expiryTime": expires_ms,
            "enable": True,
        })

        return result.get("success", False)

    async def toggle_client(
        self,
        client_id: str,
        email: str,
        enable: bool,
    ) -> bool:

        result = await self._post(f"panel/api/clients/update/{email}", {
            "email": email,
            "enable": enable,
        })

        return result.get("success", False)

    async def delete_client(self, client_id: str, email: str) -> bool:
        result = await self._post(f"panel/api/clients/del/{email}", {})
        return result.get("success", False)

    async def get_client_link(
        self,
        client_id: str,
        email: str,
        sub_id: str = "",
    ) -> str | None:

        if sub_id:
            return f"https://vpn.leftvpn.online:2096/leftsubb/{sub_id}"
        return None

    async def is_healthy(self) -> bool:
        result = await self._get("panel/api/clients/list")
        return result.get("success", False)


class XUIManager:
    """Менеджер узлов 3x-ui."""

    def __init__(self):
        self._nodes: dict[str, XUINode] = {}

    def add_node(self, name: str, node: XUINode):
        self._nodes[name] = node

    @property
    def main_node(self) -> XUINode:
        return self._nodes["main"]

    async def init_all(self):
        results = await asyncio.gather(
            *[node.login() for node in self._nodes.values()],
            return_exceptions=True,
        )

        for name, result in zip(self._nodes.keys(), results):
            if result is True:
                logger.info(f"XUI node '{name}' connected")
            else:
                logger.error(f"XUI node '{name}' connection FAILED: {result}")

    async def create_client_all_nodes(
        self,
        email: str,
        expires_at: datetime,
        total_gb: int = 0,
        inbound_ids: list[int] | None = None,  # FIX: принимаем inbound_ids извне
    ) -> tuple[bool, str, str]:

        if not self._nodes:
            return False, "", ""

        # FIX: используем переданный список, fallback на дефолт из settings
        resolved_inbound_ids = inbound_ids if inbound_ids is not None else settings.XUI_INBOUND_IDS

        ok, client_id, sub_id = await self.main_node.add_client(
            email=email,
            expires_at=expires_at,
            inbound_ids=resolved_inbound_ids,  # FIX: передаём resolved
            total_gb=total_gb,
        )

        if not ok:
            return False, "", ""

        extra_nodes = {k: v for k, v in self._nodes.items() if k != "main"}

        if extra_nodes:
            await asyncio.gather(
                *[
                    node.add_client(
                        email=email,
                        expires_at=expires_at,
                        inbound_ids=resolved_inbound_ids,  # FIX: и здесь тоже
                        total_gb=total_gb,
                    )
                    for node in extra_nodes.values()
                ],
                return_exceptions=True,
            )

        return True, client_id, sub_id

    async def delete_client_all_nodes(self, client_id: str, email: str) -> bool:
        results = await asyncio.gather(
            *[n.delete_client(client_id, email) for n in self._nodes.values()],
            return_exceptions=True,
        )
        return any(r is True for r in results)

    async def toggle_client_all_nodes(
        self,
        client_id: str,
        email: str,
        enable: bool,
    ) -> bool:

        results = await asyncio.gather(
            *[n.toggle_client(client_id, email, enable) for n in self._nodes.values()],
            return_exceptions=True,
        )

        return any(r is True for r in results)

    async def update_expiry_all_nodes(
        self,
        client_id: str,
        email: str,
        expires_at: datetime,
    ) -> bool:

        results = await asyncio.gather(
            *[n.update_client_expiry(client_id, email, expires_at) for n in self._nodes.values()],
            return_exceptions=True,
        )

        # FIX: any вместо all — достаточно чтобы хотя бы одна нода (главная) обновилась
        return any(r is True for r in results)

    async def close_all(self):
        pass


# =========================
# GLOBAL
# =========================

xui_manager = XUIManager()


def setup_xui():
    main_node = XUINode(
        host=settings.XUI_HOST,
        token=settings.XUI_TOKEN,
        node_name="main",
    )

    xui_manager.add_node("main", main_node)

    # можно добавлять дополнительные ноды:
    # xui_manager.add_node("de", XUINode(host=..., token=..., node_name="de"))