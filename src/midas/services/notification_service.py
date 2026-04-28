"""
Notification service — creates, retrieves, and manages user notifications.

Ref: specs/09 S3.3 (notification tiers), T-23-06
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class NotificationType(str, Enum):
    """Notification type taxonomy."""

    PORTFOLIO_ALERT = "PORTFOLIO_ALERT"
    REGIME_CHANGE = "REGIME_CHANGE"
    TRADE_CONFIRMATION = "TRADE_CONFIRMATION"


class NotificationService:
    """Service for creating, listing, and managing notifications."""

    def __init__(self, db: Any) -> None:
        self._db = db

    async def send(
        self,
        user_id: str,
        notification_type: NotificationType,
        title: str,
        body: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create and persist a new notification.

        Parameters
        ----------
        user_id:
            Target user identifier.
        notification_type:
            Kind of notification.
        title:
            Short title shown in notification center.
        body:
            Body text shown in the notification row.
        metadata:
            Extra context (instrument, decision_id, regime_band, etc.).

        Returns
        -------
        dict
            The created notification record.
        """
        logger.info(
            "notification.send",
            extra={
                "user_id": user_id,
                "type": notification_type.value,
                "title": title,
            },
        )
        try:
            record = await self._db.express.create(
                "notification",
                {
                    "user_id": user_id,
                    "notification_type": notification_type.value,
                    "title": title,
                    "body": body,
                    "read": False,
                    "metadata_json": json.dumps(metadata or {}),
                },
            )
            logger.info(
                "notification.sent",
                extra={"notification_id": record.get("id"), "user_id": user_id},
            )
            return record
        except Exception as exc:
            logger.error(
                "notification.send_failed",
                extra={"user_id": user_id, "error": str(exc)},
            )
            raise

    async def list_for_user(
        self,
        user_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
        unread_only: bool = False,
    ) -> list[dict[str, Any]]:
        """List notifications for a user, newest first.

        Parameters
        ----------
        user_id:
            Target user identifier.
        limit:
            Maximum number of records to return (default 50).
        offset:
            Number of records to skip (default 0).
        unread_only:
            When True, return only unread notifications.

        Returns
        -------
        list[dict]
            Notification records ordered by created_at DESC.
        """
        logger.info(
            "notification.list",
            extra={"user_id": user_id, "unread_only": unread_only, "limit": limit},
        )
        try:
            filter_opts: dict[str, Any] = {"user_id": user_id}
            if unread_only:
                filter_opts["read"] = False

            rows = await self._db.express.list(
                "notification",
                filter=filter_opts,
                limit=limit,
                offset=offset,
            )
            # Sort in Python — express.list does not support order parameter
            rows.sort(key=lambda r: r.get("id", 0), reverse=True)
            logger.info("notification.list.ok", extra={"count": len(rows), "user_id": user_id})
            return rows
        except Exception as exc:
            logger.error(
                "notification.list_failed",
                extra={"user_id": user_id, "error": str(exc)},
            )
            raise

    async def mark_read(self, notification_id: int, user_id: str) -> dict[str, Any]:
        """Mark a notification as read.

        Parameters
        ----------
        notification_id:
            ID of the notification to mark.
        user_id:
            Owner of the notification (used for authorization check).

        Returns
        -------
        dict
            The updated notification record.
        """
        logger.info(
            "notification.mark_read",
            extra={"notification_id": notification_id, "user_id": user_id},
        )
        try:
            # Fetch to verify ownership
            rows = await self._db.express.list(
                "notification",
                filter={"id": notification_id, "user_id": user_id},
            )
            if not rows:
                raise ValueError(f"Notification {notification_id} not found for user {user_id}")

            record = await self._db.express.update(
                "notification",
                notification_id,
                {"read": True},
            )
            logger.info("notification.mark_read.ok", extra={"notification_id": notification_id})
            return record
        except Exception as exc:
            logger.error(
                "notification.mark_read_failed",
                extra={"notification_id": notification_id, "error": str(exc)},
            )
            raise

    async def mark_all_read(self, user_id: str) -> int:
        """Mark all notifications for a user as read.

        Returns
        -------
        int
            Number of notifications marked as read.
        """
        logger.info("notification.mark_all_read", extra={"user_id": user_id})
        try:
            rows = await self._db.express.list(
                "notification",
                filter={"user_id": user_id, "read": False},
            )
            count = 0
            for row in rows:
                await self._db.express.update("notification", row["id"], {"read": True})
                count += 1
            logger.info("notification.mark_all_read.ok", extra={"count": count})
            return count
        except Exception as exc:
            logger.error(
                "notification.mark_all_read_failed",
                extra={"user_id": user_id, "error": str(exc)},
            )
            raise

    async def unread_count(self, user_id: str) -> int:
        """Return the count of unread notifications for a user."""
        try:
            rows = await self._db.express.list(
                "notification",
                filter={"user_id": user_id, "read": False},
            )
            return len(rows)
        except Exception as exc:
            logger.warning(
                "notification.unread_count_failed",
                extra={"user_id": user_id, "error": str(exc)},
            )
            return 0

    async def delete(self, notification_id: int, user_id: str) -> None:
        """Delete a notification.

        Parameters
        ----------
        notification_id:
            ID of the notification to delete.
        user_id:
            Owner of the notification (used for authorization check).
        """
        logger.info(
            "notification.delete",
            extra={"notification_id": notification_id, "user_id": user_id},
        )
        try:
            rows = await self._db.express.list(
                "notification",
                filter={"id": notification_id, "user_id": user_id},
            )
            if not rows:
                raise ValueError(f"Notification {notification_id} not found for user {user_id}")

            await self._db.express.delete("notification", notification_id)
            logger.info("notification.delete.ok", extra={"notification_id": notification_id})
        except Exception as exc:
            logger.error(
                "notification.delete_failed",
                extra={"notification_id": notification_id, "error": str(exc)},
            )
            raise

    # -------------------------------------------------------------------------
    # Aggregation helpers — batch routine events into digests
    # -------------------------------------------------------------------------

    async def send_or_aggregate(
        self,
        user_id: str,
        notification_type: NotificationType,
        title: str,
        body: str,
        aggregate_key: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send a notification or update an existing unread one with the same aggregate key.

        This enables batching routine events (e.g., routine rebalances) into a single
        notification that updates with the latest info rather than flooding the inbox.

        Parameters
        ----------
        user_id:
            Target user identifier.
        notification_type:
            Kind of notification.
        title:
            Notification title.
        body:
            Latest body text (updated on existing unread notification).
        aggregate_key:
            When set, look for an existing unread notification with the same key
            and update it instead of creating a new one.
        metadata:
            Extra context.

        Returns
        -------
        dict
            The created or updated notification record.
        """
        if aggregate_key:
            existing = await self._db.express.list(
                "notification",
                filter={
                    "user_id": user_id,
                    "notification_type": notification_type.value,
                    "read": False,
                    "metadata_json": json.dumps({"aggregate_key": aggregate_key}),
                },
            )
            if existing:
                return await self._db.express.update(
                    "notification",
                    existing[0]["id"],
                    {"body": body, "metadata_json": json.dumps(metadata or {})},
                )

        return await self.send(user_id, notification_type, title, body, metadata)
