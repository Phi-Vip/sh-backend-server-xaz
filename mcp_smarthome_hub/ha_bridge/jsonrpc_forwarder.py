# -*- coding: utf-8 -*-
"""BỘ CHUYỂN TIẾP LỆNH CHUẨN MCP JSON-RPC 2.0 LIÊN NODE CHO HOME ASSISTANT (JSON-RPC FORWARDER).

Nhiệm vụ:
1. Đóng gói lệnh điều khiển theo đúng chuẩn JSON-RPC 2.0 (RFC 7159) & đặc tả Model Context Protocol (MCP).
2. Tự động định tuyến tối ưu:
   - Nếu HA Client kết nối trên cùng Node: Gửi trực tiếp qua socket với RTT < 2ms.
   - Nếu HA Client kết nối ở Node khác: Chuyển tiếp liên node qua Redis Pub/Sub (ha:cmd:{node} & ha:res:{req_id}) với RTT < 15ms.
3. Hỗ trợ chuẩn hóa các hàm nghiệp vụ Home Assistant:
   - `ha_call_service`: Bật/tắt đèn, công tắc, điều hòa, rèm cửa, gọi automation.
   - `ha_get_states`: Lấy danh sách thực thể (Entities) và trạng thái hiện tại.
4. Bọc màng bảo vệ Hard Timeout, bảo toàn thời gian thực cho luồng âm thanh XiaoZhi Voice Core.
"""

import time
import uuid
import logging
from typing import Any, Dict, List, Optional

from .redis_session_mgr import RedisSessionManager
from .ha_tunnel_server import HATunnelServer

logger = logging.getLogger("HAJsonRpcForwarder")


class HAForwarderException(Exception):
    """Ngoại lệ phát sinh trong quá trình chuyển tiếp lệnh Home Assistant."""
    pass


class HAUserOfflineException(HAForwarderException):
    """Ngoại lệ khi người dùng chưa kết nối đường hầm Home Assistant."""
    pass


class JSONRPCForwarder:
    """Bộ chuyển tiếp lệnh JSON-RPC 2.0 xuyên cụm phân tán đa node."""

    def __init__(
        self,
        tunnel_server: HATunnelServer,
        session_mgr: Optional[RedisSessionManager] = None,
    ):
        """Khởi tạo Forwarder liên kết với TunnelServer và SessionManager."""
        self.tunnel_server = tunnel_server
        self.session_mgr = session_mgr or tunnel_server.session_mgr

    # =========================================================================
    # Lõi Điều Phối Lệnh JSON-RPC 2.0 (Core Dispatcher)
    # =========================================================================

    async def forward_request(
        self,
        user_id: str,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: float = 2.5,
    ) -> Dict[str, Any]:
        """Gửi yêu cầu JSON-RPC 2.0 tới Home Assistant của User và đón nhận kết quả."""
        start_time = time.perf_counter()
        req_id = f"mcp_{uuid.uuid4().hex[:8]}"

        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params or {},
        }

        # 1. Tra cứu Node đang giữ kết nối của User
        target_node = await self.session_mgr.get_session_node(user_id)
        if not target_node:
            logger.warning(f"Không thể chuyển tiếp lệnh: User [{user_id}] hiện đang OFFLINE!")
            raise HAUserOfflineException(
                f"Đường hầm Home Assistant của người dùng [{user_id}] hiện đang ngoại tuyến hoặc chưa ghép nối!"
            )

        # 2. TRƯỜNG HỢP A: KẾT NỐI NẰM NGAY TRÊN NODE CỤC BỘ (RTT SIÊU TỐC < 5MS)
        if target_node == self.session_mgr.node_id and self.tunnel_server.is_user_local(user_id):
            logger.debug(f"Định tuyến cục bộ: User [{user_id}] ➔ Local Node [{self.session_mgr.node_id}]")
            response = await self.tunnel_server.send_to_local_user(
                user_id=user_id,
                payload=payload,
                timeout=timeout,
            )
            rtt_ms = (time.perf_counter() - start_time) * 1000
            logger.info(f"⚡ [LOCAL FORWARD]: Lệnh '{method}' hoàn tất trong {rtt_ms:.2f}ms")
            return self._unwrap_response(response)

        # 3. TRƯỜNG HỢP B: KẾT NỐI NẰM TRÊN NODE KHÁC (REDIS PUB/SUB BRIDGE - RTT < 25MS)
        logger.info(
            f"🌐 [CROSS-NODE FORWARD]: Chuyển tiếp lệnh từ [{self.session_mgr.node_id}] ➔ Node [{target_node}] "
            f"cho User [{user_id}] qua Redis"
        )

        cmd_envelope = {
            "req_id": req_id,
            "user_id": user_id,
            "caller_node": self.session_mgr.node_id,
            "payload": payload,
            "timestamp": time.time(),
        }

        # Bắn lệnh tới Node đích
        publish_ok = await self.session_mgr.publish_command(target_node, cmd_envelope)
        if not publish_ok:
            raise HAForwarderException(f"Không thể gửi lệnh qua kênh mạng tới Node [{target_node}]")

        # Đợi phản hồi từ Node đích qua kênh ha:res:{req_id}
        try:
            response = await self.session_mgr.wait_for_response(req_id, timeout=timeout)
            rtt_ms = (time.perf_counter() - start_time) * 1000
            logger.info(f"⚡ [REDIS BRIDGE]: Lệnh liên node '{method}' hoàn tất trong {rtt_ms:.2f}ms (Target: {target_node})")
            return self._unwrap_response(response)
        except TimeoutError:
            rtt_ms = (time.perf_counter() - start_time) * 1000
            logger.error(f"❌ [TIMEOUT]: Quá thời gian ({timeout}s, RTT={rtt_ms:.2f}ms) chờ phản hồi từ Node [{target_node}]")
            raise TimeoutError(f"Quá thời hạn chờ Home Assistant phản hồi lệnh ({timeout}s)")

    def _unwrap_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Bóc tách và xác thực kết quả JSON-RPC 2.0."""
        if "error" in response:
            err = response["error"]
            err_msg = err.get("message", "Lỗi không xác định từ Home Assistant")
            err_code = err.get("code", -32000)
            logger.warning(f"Home Assistant trả về lỗi (code {err_code}): {err_msg}")
            raise HAForwarderException(f"Lỗi Home Assistant [{err_code}]: {err_msg}")

        return response.get("result", {})

    # =========================================================================
    # Nghiệp Vụ Điều Khiển Thiết Bị Cụ Thể (High-Level HA Helpers)
    # =========================================================================

    async def call_service(
        self,
        user_id: str,
        domain: str,
        service: str,
        target: Optional[Dict[str, Any]] = None,
        service_data: Optional[Dict[str, Any]] = None,
        timeout: float = 2.5,
    ) -> Dict[str, Any]:
        """Gọi một dịch vụ (service) trong Home Assistant (Ví dụ: light.turn_on, switch.toggle)."""
        params = {
            "domain": domain,
            "service": service,
            "target": target or {},
            "service_data": service_data or {},
        }
        return await self.forward_request(
            user_id=user_id,
            method="homeassistant.call_service",
            params=params,
            timeout=timeout,
        )

    async def get_states(
        self,
        user_id: str,
        timeout: float = 3.0,
    ) -> List[Dict[str, Any]]:
        """Lấy toàn bộ danh sách trạng thái thực thể của Home Assistant để tiêm ngữ cảnh LLM."""
        res = await self.forward_request(
            user_id=user_id,
            method="homeassistant.get_states",
            params={},
            timeout=timeout,
        )
        if isinstance(res, list):
            return res
        return res.get("states", [])

