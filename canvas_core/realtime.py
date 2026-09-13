"""实时通知：连接独立限时、串行发送，并行广播；单个坏连接不阻塞其他页面。"""
import asyncio
import json
import logging
import time

log = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self, send_timeout=2.0):
        self.send_timeout = send_timeout
        self.active_connections = []
        self.user_connections = {}
        self.connection_clients = {}
        self._send_locks = {}

    async def connect(self, websocket, client_id=None):
        await websocket.accept()
        if websocket not in self.active_connections:
            self.active_connections.append(websocket)
        self.connection_clients[websocket] = client_id or f'anon-{id(websocket)}'
        self._send_locks.setdefault(websocket, asyncio.Lock())
        if client_id:
            self.user_connections[client_id] = websocket
        await self.broadcast_count()

    def _forget(self, websocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        client_id = self.connection_clients.pop(websocket, None)
        if self.user_connections.get(client_id) is websocket:
            self.user_connections.pop(client_id, None)
        self._send_locks.pop(websocket, None)

    async def disconnect(self, websocket, client_id=None):
        self._forget(websocket)
        await self.broadcast_count()

    def online_count(self):
        return len({client for client in self.connection_clients.values()
                    if client and not str(client).startswith('canvas_')})

    async def _send_encoded(self, websocket, data):
        lock = self._send_locks.get(websocket)
        if lock is None:
            return False
        async def deliver():
            async with lock:
                if websocket in self.connection_clients:
                    await websocket.send_text(data)
                    return True
                return False
        try:
            return await asyncio.wait_for(deliver(), timeout=self.send_timeout)
        except Exception:
            # 不输出消息正文、素材内容或客户端标识。
            log.warning('实时连接发送失败或超时，已移除该连接')
            self._forget(websocket)
            if hasattr(websocket, 'close'):
                try:
                    await asyncio.wait_for(websocket.close(code=1011), timeout=min(0.25, self.send_timeout))
                except Exception:
                    pass
            return False

    async def send(self, websocket, message):
        return await self._send_encoded(websocket, json.dumps(message))

    async def _broadcast(self, message):
        data = json.dumps(message)
        await asyncio.gather(*(self._send_encoded(ws, data) for ws in tuple(self.active_connections)))

    async def broadcast_count(self):
        await self._broadcast({'type': 'stats', 'online_count': self.online_count()})

    async def broadcast_new_image(self, image_data):
        await self._broadcast({'type': 'new_image', 'data': image_data})

    async def broadcast_canvas_updated(self, canvas_id, updated_at, revision=0, client_id=''):
        await self._broadcast({'type': 'canvas_updated', 'canvas_id': canvas_id,
                               'updated_at': updated_at, 'revision': revision, 'client_id': client_id or ''})

    async def broadcast_asset_library_updated(self, updated_at=0):
        await self._broadcast({'type': 'asset_library_updated', 'updated_at': updated_at or int(time.time() * 1000)})

    async def send_personal_message(self, message, client_id):
        websocket = self.user_connections.get(client_id)
        if websocket is not None:
            return await self.send(websocket, message)
        return False
