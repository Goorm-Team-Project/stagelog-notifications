from typing import Optional
from uuid import uuid4

from django.utils import timezone

from common.models import OutboxEvent


NOTIFICATION_DETAIL_TYPE_MAP = {
    "comment": "notification.comment.created",
    "post_like": "notification.post.liked",
    "post_dislike": "notification.post.disliked",
    "event": "notification.event.updated",
    "notice": "notification.system.broadcast",
}


def _to_detail_type(notification_type: str) -> str:
    return NOTIFICATION_DETAIL_TYPE_MAP.get(notification_type, "notification.system.broadcast")


def create_notification(
    user_id: int,
    type: str,
    message: str,
    relate_url: Optional[str] = None,
    post: Optional[object] = None,
    event: Optional[object] = None,
    database: str = "default",
    source: Optional[str] = None,
):
    """
    알림 엔티티를 직접 저장하지 않고 outbox 이벤트를 적재한다.
    outbox 워커는 event_type(detail-type) + payload(detail)로 EventBridge에 발행한다.
    """
    try:
        now = timezone.now()
        detail_type = _to_detail_type(type)
        payload = {
            "event_id": str(uuid4()),
            "schema_version": "v1",
            "source": source or "stagelog.core",
            "detail_type": detail_type,
            "occurred_at": now.isoformat(),
            "recipient_user_id": user_id,
            "type": type,
            "message": message,
            "relate_url": relate_url,
            "post_id": getattr(post, "post_id", None),
            "related_event_id": getattr(event, "event_id", None),
        }

        OutboxEvent.objects.using(database).create(
            aggregate_type="notification",
            aggregate_id=str(user_id),
            event_type=detail_type,
            payload=payload,
            available_at=now,
        )
    except Exception as e:
        print(f"알림 생성 실패: {e}")
