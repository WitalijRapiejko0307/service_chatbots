"""PostgreSQL storage for audit logs."""

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Optional

from app.storage.postgres import _parse_json, get_pool
from app.utils.datetime_utils import to_utc_iso_string, utc_now

logger = logging.getLogger(__name__)


class PostgresAuditStorage:
    """CRUD operations for audit logs."""

    async def create_audit_log(
        self,
        admin_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        # Include a UUID so two actions on the same resource in one second do not collide.
        log_id = f"{resource_type}_{resource_id}_{uuid.uuid4().hex}"
        meta = json.dumps(metadata or {})
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO audit_logs (log_id, admin_id, action, resource_type, resource_id, timestamp, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
                """,
                log_id,
                admin_id,
                action,
                resource_type,
                resource_id,
                utc_now(),
                meta,
            )
        return {
            "log_id": log_id,
            "admin_id": admin_id,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "timestamp": to_utc_iso_string(utc_now()),
            "metadata": metadata or {},
        }

    async def list_audit_logs(
        self,
        admin_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        action: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        sort_desc: bool = True,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        where = []
        params = []
        i = 1
        if admin_id:
            where.append(f"admin_id = ${i}")
            params.append(admin_id)
            i += 1
        if resource_type:
            where.append(f"resource_type = ${i}")
            params.append(resource_type)
            i += 1
        if action:
            where.append(f"action = ${i}")
            params.append(action)
            i += 1
        if start_date is not None:
            where.append(f"timestamp >= ${i}")
            params.append(start_date)
            i += 1
        if end_date is not None:
            where.append(f"timestamp <= ${i}")
            params.append(end_date)
            i += 1
        params.append(limit)
        clause = " AND ".join(where) if where else "TRUE"
        order = "DESC" if sort_desc else "ASC"
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT * FROM audit_logs WHERE {clause} ORDER BY timestamp {order} LIMIT ${i}",
                *params,
            )
        items = []
        for r in rows:
            d = dict(r)
            if "metadata" in d and isinstance(d["metadata"], str):
                d["metadata"] = _parse_json(d["metadata"])
            if "timestamp" in d and isinstance(d["timestamp"], datetime):
                d["timestamp"] = to_utc_iso_string(d["timestamp"])
            items.append(d)
        return items
