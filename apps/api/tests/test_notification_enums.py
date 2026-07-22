"""The DB notification enum and the API response enum must stay in lock-step.

If a member exists in the database enum but not in the response schema, writing
that notification succeeds but *reading it back* raises a pydantic
ValidationError inside ``list_for_user`` — which 500s the recipient's entire
inbox, not just the offending row. Counting unread notifications still works,
so this failure hides from any test that only checks counts.
"""

from __future__ import annotations

from victus_api.db.models import NotificationType as DbNotificationType
from victus_api.notifications.schemas import NotificationType as ApiNotificationType


def test_notification_enums_match_member_for_member() -> None:
    db_members = {m.value for m in DbNotificationType}
    api_members = {m.value for m in ApiNotificationType}

    missing_from_api = db_members - api_members
    assert not missing_from_api, (
        "notifications/schemas.NotificationType is missing "
        f"{sorted(missing_from_api)} — reading one of these 500s the inbox."
    )

    unknown_to_db = api_members - db_members
    assert not unknown_to_db, (
        f"notifications/schemas.NotificationType has {sorted(unknown_to_db)} "
        "with no corresponding database enum value."
    )
