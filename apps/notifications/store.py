from typing import Dict, List, Optional, Union

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from django.conf import settings


def _notification_table():
    dynamodb = boto3.resource("dynamodb", region_name=settings.AWS_REGION)
    return dynamodb.Table(settings.NOTIFICATION_DDB_TABLE_NAME)


def _user_pk(user_id: int) -> str:
    return f"USER#{int(user_id)}"


def _notification_sk(notification_id: Union[int, str]) -> str:
    return f"NOTI#{int(str(notification_id))}"


def _meta_counts_sk() -> str:
    return "META#COUNTS"


def _item_to_notification(item: Dict) -> Dict:
    return {
        # Keep IDs as strings so the frontend does not lose precision.
        "notification_id": str(int(item["notification_id"])),
        "type": item.get("type"),
        "message": item.get("message"),
        "is_read": bool(item.get("is_read", False)),
        "created_at": item.get("created_at"),
        "post_id": item.get("post_id"),
        "event_id": item.get("related_event_id"),
        "relate_url": item.get("relate_url"),
        "_pk": item.get("pk"),
        "_sk": item.get("sk"),
    }


def _list_notification_items(user_id: int) -> List[Dict]:
    table = _notification_table()
    items: List[Dict] = []
    kwargs = {
        "IndexName": "gsi1",
        "KeyConditionExpression": Key("gsi1pk").eq(_user_pk(user_id)),
        "ScanIndexForward": False,
    }

    while True:
        response = table.query(**kwargs)
        items.extend(response.get("Items", []))
        last_evaluated_key = response.get("LastEvaluatedKey")
        if not last_evaluated_key:
            break
        kwargs["ExclusiveStartKey"] = last_evaluated_key

    return items


def list_notifications(user_id: int, *, type_filter: Optional[str] = None) -> List[Dict]:
    items = _list_notification_items(user_id)
    notifications = [_item_to_notification(item) for item in items]
    if type_filter:
        notifications = [row for row in notifications if row.get("type") == type_filter]
    return notifications


def unread_count(user_id: int) -> int:
    table = _notification_table()
    response = table.get_item(
        Key={
            "pk": _user_pk(user_id),
            "sk": _meta_counts_sk(),
        }
    )
    item = response.get("Item") or {}
    return max(0, int(item.get("unread_count") or 0))


def mark_notification_read(user_id: int, notification_id: Union[int, str]) -> bool:
    table = _notification_table()
    key = {
        "pk": _user_pk(user_id),
        "sk": _notification_sk(notification_id),
    }
    response = table.get_item(Key=key)
    target = response.get("Item")
    if not target:
        return False

    if bool(target.get("is_read", False)):
        return True

    try:
        table.update_item(
            Key=key,
            ConditionExpression="attribute_exists(pk) AND attribute_exists(sk) AND is_read = :false",
            UpdateExpression="SET is_read = :true",
            ExpressionAttributeValues={":true": True, ":false": False},
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
            raise
        return True

    table.update_item(
        Key={
            "pk": _user_pk(user_id),
            "sk": _meta_counts_sk(),
        },
        UpdateExpression="SET unread_count = if_not_exists(unread_count, :zero) - :one",
        ExpressionAttributeValues={":zero": 0, ":one": 1},
    )

    return True
