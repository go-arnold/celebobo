STAFF = "staff"
PRESENCE = "presence.resellers"


def user_group(user_id: int) -> str:
    return f"user.{user_id}"


def conversation_group(conversation_id: int) -> str:
    return f"conversation.{conversation_id}"
