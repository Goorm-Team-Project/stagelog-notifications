import hashlib
import json
import logging
from datetime import timedelta

import boto3
import redis
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


def _sqs_client():
    return boto3.client("sqs", region_name=settings.AWS_REGION)


def _notification_table():
    dynamodb = boto3.resource("dynamodb", region_name=settings.AWS_REGION)
    return dynamodb.Table(settings.NOTIFICATION_DDB_TABLE_NAME)


def _redis_client():
    return redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        password=settings.REDIS_PASSWORD or None,
        ssl=settings.REDIS_SSL,
        decode_responses=True,
        socket_timeout=1,
        socket_connect_timeout=1,
    )


def _stable_notification_id(sk: str) -> int:
    digest = hashlib.sha256(sk.encode("utf-8")).hexdigest()
    return int(digest[:13], 16)


def _parse_sqs_message_body(body: str) -> dict:
    """
    EventBridge -> SQS 표준 형태를 파싱한다.
    body 예시:
      {
        "version": "...",
        "id": "...",
        "detail-type": "...",
        "source": "...",
        "detail": { ... } 또는 "detail": "{...json...}"
      }
    """
    outer = json.loads(body or "{}")
    detail = outer.get("detail", {})
    if isinstance(detail, str):
        try:
            detail = json.loads(detail)
        except json.JSONDecodeError:
            detail = {}
    if not isinstance(detail, dict):
        detail = {}
    return detail


def _to_dynamodb_item(detail: dict) -> dict:
    now = timezone.now()
    occurred_at = detail.get("occurred_at") or now.isoformat()
    event_id = detail.get("event_id") or f"missing-{int(now.timestamp() * 1000)}"
    user_id = str(detail.get("recipient_user_id") or "unknown")
    ttl = int((now + timedelta(days=settings.NOTIFICATION_DDB_TTL_DAYS)).timestamp())
    sk = f"NOTI#{occurred_at}#{event_id}"

    return {
        "pk": f"USER#{user_id}",
        "sk": sk,
        "gsi1pk": f"USER#{user_id}",
        "gsi1sk": occurred_at,
        "notification_id": _stable_notification_id(sk),
        "event_id": event_id,
        "recipient_user_id": int(detail.get("recipient_user_id") or 0),
        "type": detail.get("type", "notice"),
        "message": detail.get("message", ""),
        "relate_url": detail.get("relate_url"),
        "post_id": detail.get("post_id"),
        "event_ref_id": detail.get("related_event_id"),
        "is_read": False,
        "created_at": occurred_at,
        "ttl": ttl,
    }


def _mark_event_deduped(rds, event_id: str) -> bool:
    """
    True: 처음 처리 이벤트
    False: 이미 처리된 이벤트(중복)
    """
    if not event_id:
        return True
    key = f"noti:dedupe:event:{event_id}"
    created = rds.set(key, "1", ex=settings.NOTIFICATION_DEDUPE_TTL_SECONDS, nx=True)
    return bool(created)


def _incr_unread_cache(rds, user_id: int):
    if not user_id:
        return
    key = f"noti:unread:{user_id}"
    rds.incr(key)
    rds.expire(key, settings.NOTIFICATION_UNREAD_CACHE_TTL_SECONDS)


def consume_notification_batch(
    *,
    queue_url: str,
    max_messages: int = 10,
    wait_time_seconds: int = 20,
):
    if not queue_url:
        logger.warning("notification_consumer empty_queue_url")
        return {"received": 0, "saved": 0, "deleted": 0, "failed": 0, "reason": "empty_queue_url"}

    sqs = _sqs_client()
    table = _notification_table()
    redis_client = None
    if settings.REDIS_HOST:
        try:
            redis_client = _redis_client()
            redis_client.ping()
        except Exception:
            logger.warning("notification_consumer redis_unavailable")
            redis_client = None

    receive_kwargs = {
        "QueueUrl": queue_url,
        "MaxNumberOfMessages": max(1, min(max_messages, 10)),
        "WaitTimeSeconds": max(0, min(wait_time_seconds, 20)),
    }

    response = sqs.receive_message(**receive_kwargs)
    messages = response.get("Messages", [])
    if not messages:
        logger.info("notification_consumer received=0 saved=0 deleted=0 failed=0")
        return {"received": 0, "saved": 0, "deleted": 0, "failed": 0}

    logger.info("notification_consumer batch_start received=%s", len(messages))

    saved = 0
    deleted = 0
    failed = 0

    for msg in messages:
        receipt_handle = msg.get("ReceiptHandle")
        detail = {}
        try:
            detail = _parse_sqs_message_body(msg.get("Body", ""))
            event_id = detail.get("event_id")
            if redis_client and not _mark_event_deduped(redis_client, event_id):
                logger.info(
                    "notification_consumer duplicate event_id=%s user_id=%s source=redis",
                    detail.get("event_id"),
                    detail.get("recipient_user_id"),
                )
                if receipt_handle:
                    sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
                    deleted += 1
                continue

            item = _to_dynamodb_item(detail)
            table.put_item(
                Item=item,
                ConditionExpression="attribute_not_exists(pk) AND attribute_not_exists(sk)",
            )
            saved += 1
            logger.info(
                "notification_consumer saved event_id=%s user_id=%s notification_id=%s",
                detail.get("event_id"),
                item.get("recipient_user_id"),
                item.get("notification_id"),
            )
            if redis_client:
                _incr_unread_cache(redis_client, item.get("recipient_user_id"))

            if receipt_handle:
                sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
                deleted += 1
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code == "ConditionalCheckFailedException":
                logger.info(
                    "notification_consumer duplicate event_id=%s user_id=%s source=dynamodb",
                    detail.get("event_id"),
                    detail.get("recipient_user_id"),
                )
                if receipt_handle:
                    sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
                    deleted += 1
                continue
            logger.warning(
                "notification_consumer client_error event_id=%s user_id=%s code=%s",
                detail.get("event_id"),
                detail.get("recipient_user_id"),
                error_code,
            )
            failed += 1
            continue
        except (json.JSONDecodeError, BotoCoreError, ValueError, TypeError):
            # 저장/파싱 실패 시 delete하지 않고 재시도 또는 DLQ로 이동시킨다.
            logger.exception(
                "notification_consumer failed event_id=%s user_id=%s",
                detail.get("event_id"),
                detail.get("recipient_user_id"),
            )
            failed += 1
            continue

    logger.info(
        "notification_consumer batch_end received=%s saved=%s deleted=%s failed=%s",
        len(messages),
        saved,
        deleted,
        failed,
    )
    return {"received": len(messages), "saved": saved, "deleted": deleted, "failed": failed}
