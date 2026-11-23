# -*- coding: utf-8 -*-
"""Gói Routers REST API cho SmartHome MCP Hub."""

from .pairing_router import create_pairing_router
from .esunhouse_router import create_esunhouse_router
from .tuya_auth_router import create_tuya_auth_router
from .portal_router import create_portal_router
from .ota_pairing_router import create_ota_pairing_router
from .agent_profile_router import create_agent_profile_router, invalidate_agent_cache_in_redis

__all__ = [
    "create_pairing_router",
    "create_esunhouse_router",
    "create_tuya_auth_router",
    "create_portal_router",
    "create_ota_pairing_router",
    "create_agent_profile_router",
    "invalidate_agent_cache_in_redis",
]
