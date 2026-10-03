from typing import Any, cast

from config.settings import base


def test_database_connections_time_out():
    assert base.DATABASES["default"]["OPTIONS"]["connect_timeout"] > 0


def test_redis_connections_time_out_and_are_checked():
    cache_options = cast(dict[str, Any], base.CACHES["default"]["OPTIONS"])
    (channels_host,) = cast(dict[str, Any], base.CHANNEL_LAYERS["default"]["CONFIG"])["hosts"]

    assert cache_options["socket_timeout"] > 0
    assert cache_options["socket_connect_timeout"] > 0
    assert channels_host["socket_connect_timeout"] > 0
    assert base.CELERY_BROKER_TRANSPORT_OPTIONS["socket_timeout"] > 0


def test_outgoing_email_and_tasks_are_bounded():
    assert base.EMAIL_TIMEOUT > 0
    assert base.CELERY_TASK_SOFT_TIME_LIMIT < base.CELERY_TASK_TIME_LIMIT
