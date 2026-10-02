from django.db import connection

from apps.analytics.models import FACTS_VIEW


class FactsRefresher:
    def refresh(self, *, concurrently: bool = True) -> None:
        mode = "CONCURRENTLY " if concurrently else ""
        with connection.cursor() as cursor:
            cursor.execute(f"REFRESH MATERIALIZED VIEW {mode}{FACTS_VIEW}")
