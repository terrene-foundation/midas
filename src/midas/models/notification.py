"""
Notification Pydantic models for API request/response validation.

Ref: T-23-06
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class NotificationTypeEnum(str, Enum):
    """Notification type taxonomy matching NotificationType in the service."""

    PORTFOLIO_ALERT = "PORTFOLIO_ALERT"
    REGIME_CHANGE = "REGIME_CHANGE"
    TRADE_CONFIRMATION = "TRADE_CONFIRMATION"


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class NotificationResponse(BaseModel):
    """A single notification record."""

    id: int
    user_id: str
    notification_type: NotificationTypeEnum
    title: str
    body: str
    read: bool
    metadata_json: str = "{}"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class NotificationListResponse(BaseModel):
    """Paginated list of notifications."""

    items: list[NotificationResponse]
    total: int
    unread_count: int
    limit: int
    offset: int


class NotificationPreferencesResponse(BaseModel):
    """User notification preferences."""

    tiers: dict[str, str] = Field(
        default_factory=lambda: {
            "calm": "silent_in_app",
            "elevated": "standard_push",
            "urgent": "prominent_push_haptic",
            "crisis": "emergency",
        }
    )
    quiet_hours: dict[str, str] = Field(
        default_factory=lambda: {
            "start": "22:00",
            "end": "07:00",
            "timezone": "Asia/Singapore",
        }
    )
    daily_attention_ceiling_minutes: int = 30
    portfolio_alerts_enabled: bool = True
    regime_change_enabled: bool = True
    trade_confirmations_enabled: bool = True


class NotificationPreferencesUpdate(BaseModel):
    """Payload for updating notification preferences."""

    tiers: dict[str, str] | None = None
    quiet_hours: dict[str, str] | None = None
    daily_attention_ceiling_minutes: int | None = Field(default=None, ge=5, le=120)
    portfolio_alerts_enabled: bool | None = None
    regime_change_enabled: bool | None = None
    trade_confirmations_enabled: bool | None = None


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class NotificationSendRequest(BaseModel):
    """Internal payload for creating a notification (used by agents/jobs)."""

    user_id: str
    notification_type: NotificationTypeEnum
    title: str = Field(max_length=200)
    body: str = Field(max_length=1000)
    metadata: dict[str, Any] = Field(default_factory=dict)
    aggregate_key: str | None = None


class MarkReadRequest(BaseModel):
    """Mark a notification as read."""

    notification_id: int


class MarkAllReadRequest(BaseModel):
    """Mark all notifications as read for the current user."""
