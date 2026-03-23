import json
import logging
from datetime import timedelta

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


def _user_pk(user_id: int) -> str:
    return f"USER#{int(user_id)}"


def _notification_sk(notification_id: int) -> str:
    return f"NOTI#{int(notification_id)}"


def _meta_counts_sk() -> str:
    return "META#COUNTS"


def _sqs_client():
    return boto3.client("sqs", region_name=settings.AWS_REGION)


def _notification_table():
    dynamodb = boto3.resource("dynamodb", region_name=settings.AWS_REGION)
    return dynamodb.Table(settings.NOTIFICATION_DDB_TABLE_NAME)


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
    user_id = int(detail.get("recipient_user_id") or 0)
    ttl = int((now + timedelta(days=settings.NOTIFICATION_DDB_TTL_DAYS)).timestamp())
    notification_seed = f"USER#{user_id}#EVENT#{event_id}#AT#{occurred_at}"
    # Keep the original seed/hash shape so notification_id is stable and
    # can be used as part of the direct primary key lookup on read.
    import hashlib

    notification_id = int(hashlib.sha256(notification_seed.encode("utf-8")).hexdigest()[:15], 16)

    return {
        "pk": _user_pk(user_id),
        "sk": _notification_sk(notification_id),
        "gsi1pk": _user_pk(user_id),
        "gsi1sk": f"TS#{occurred_at}#{notification_id}",
        "notification_id": notification_id,
        "event_id": event_id,
        "recipient_user_id": user_id,
        "type": detail.get("type", "notice"),
        "message": detail.get("message", ""),
        "relate_url": detail.get("relate_url"),
        "post_id": detail.get("post_id"),
        "related_event_id": detail.get("related_event_id"),
        "is_read": False,
        "created_at": occurred_at,
        "ttl": ttl,
    }


def _incr_unread_count(table, user_id: int):
    table.update_item(
        Key={
            "pk": _user_pk(user_id),
            "sk": _meta_counts_sk(),
        },
        UpdateExpression="SET unread_count = if_not_exists(unread_count, :zero) + :one, updated_at = :updated_at",
        ExpressionAttributeValues={
            ":zero": 0,
            ":one": 1,
            ":updated_at": timezone.now().isoformat(),
        },
    )


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
            item = _to_dynamodb_item(detail)
            table.put_item(
                Item=item,
                ConditionExpression="attribute_not_exists(pk) AND attribute_not_exists(sk)",
            )
            _incr_unread_count(table, item.get("recipient_user_id"))
            saved += 1
            logger.info(
                "notification_consumer saved event_id=%s user_id=%s notification_id=%s",
                detail.get("event_id"),
                item.get("recipient_user_id"),
                item.get("notification_id"),
            )

            if receipt_handle:
                sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
                deleted += 1
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code == "ConditionalCheckFailedException":
                logger.info(
                    "notification_consumer duplicate event_id=%s user_id=%s",
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
