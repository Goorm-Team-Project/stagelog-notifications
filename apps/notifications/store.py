import hashlib
from typing import Dict, List, Optional

import boto3
import redis
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from django.conf import settings


def _notification_table():
    dynamodb = boto3.resource("dynamodb", region_name=settings.AWS_REGION)
    return dynamodb.Table(settings.NOTIFICATION_DDB_TABLE_NAME)


def _user_pk(user_id: int) -> str:
    return f"USER#{int(user_id)}"


def _redis_client():
    if not settings.REDIS_HOST:
        return None
    try:
        client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD or None,
            ssl=settings.REDIS_SSL,
            decode_responses=True,
            socket_timeout=1,
            socket_connect_timeout=1,
        )
        client.ping()
        return client
    except Exception:
        return None


def _stable_notification_id(sk: str) -> int:
    digest = hashlib.sha256(sk.encode("utf-8")).hexdigest()
    return int(digest[:13], 16)


def _item_to_notification(item: Dict) -> Dict:
    sk = str(item.get("sk") or "")
    return {
        "notification_id": int(item.get("notification_id") or _stable_notification_id(sk)),
        "type": item.get("type"),
        "message": item.get("message"),
        "is_read": bool(item.get("is_read", False)),
        "created_at": item.get("created_at"),
        "post_id": item.get("post_id"),
        "event_id": item.get("event_ref_id") or item.get("related_event_id"),
        "relate_url": item.get("relate_url"),
        "_pk": item.get("pk"),
        "_sk": sk,
    }


def _query_all(table, **kwargs) -> List[Dict]:
    items: List[Dict] = []
    while True:
        response = table.query(**kwargs)
        items.extend(response.get("Items", []))
        last_evaluated_key = response.get("LastEvaluatedKey")
        if not last_evaluated_key:
            break
        kwargs["ExclusiveStartKey"] = last_evaluated_key
    return items


def _query_all_user_items(user_id: int) -> List[Dict]:
    table = _notification_table()
    try:
        items = _query_all(
            table,
            IndexName="gsi1",
            KeyConditionExpression=Key("gsi1pk").eq(_user_pk(user_id)),
            ScanIndexForward=False,
        )
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code")
        if error_code not in {"ValidationException", "ResourceNotFoundException"}:
            raise
        items = _query_all(
            table,
            KeyConditionExpression=Key("pk").eq(_user_pk(user_id)),
            ScanIndexForward=False,
        )

    return [item for item in items if str(item.get("sk") or "").startswith("NOTI#")]


def list_notifications(user_id: int, *, type_filter: Optional[str] = None) -> List[Dict]:
    notifications = [_item_to_notification(item) for item in _query_all_user_items(user_id)]
    if type_filter:
        notifications = [row for row in notifications if row.get("type") == type_filter]
    return notifications


def unread_count(user_id: int) -> int:
    redis_client = _redis_client()
    if redis_client:
        cached = redis_client.get(f"noti:unread:{int(user_id)}")
        if cached is not None:
            try:
                return max(0, int(cached))
            except (TypeError, ValueError):
                pass

    count = sum(1 for row in list_notifications(user_id) if not row.get("is_read"))
    if redis_client:
        redis_client.setex(
            f"noti:unread:{int(user_id)}",
            settings.NOTIFICATION_UNREAD_CACHE_TTL_SECONDS,
            count,
        )
    return count


def mark_notification_read(user_id: int, notification_id: int) -> bool:
    table = _notification_table()
    target = None
    for item in _query_all_user_items(user_id):
        current_id = int(item.get("notification_id") or _stable_notification_id(str(item.get("sk") or "")))
        if current_id == int(notification_id):
            target = item
            break

    if not target:
        return False

    if bool(target.get("is_read", False)):
        return True

    table.update_item(
        Key={
            "pk": target["pk"],
            "sk": target["sk"],
        },
        UpdateExpression="SET is_read = :true",
        ExpressionAttributeValues={":true": True},
    )

    redis_client = _redis_client()
    if redis_client:
        cache_key = f"noti:unread:{int(user_id)}"
        try:
            unread = redis_client.decr(cache_key)
            if unread < 0:
                redis_client.setex(cache_key, settings.NOTIFICATION_UNREAD_CACHE_TTL_SECONDS, 0)
        except Exception:
            pass

    return True
