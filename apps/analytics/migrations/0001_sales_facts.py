from zoneinfo import ZoneInfo

from django.apps.registry import Apps
from django.conf import settings
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

FACTS_SQL = """
CREATE MATERIALIZED VIEW analytics_sales_fact AS
SELECT
    date_trunc('hour', sale.sold_at, '{tz}') AS bucket,
    sale.product_id,
    product.category_id,
    sale.seller_id,
    sale.payment_method,
    count(*) FILTER (WHERE sale.status <> 'returned')::integer AS sales_count,
    coalesce(sum(sale.quantity) FILTER (WHERE sale.status <> 'returned'), 0)::integer AS units,
    sum(sale.unit_price * sale.quantity - sale.refunded_amount)::numeric(14, 2) AS revenue,
    coalesce(
        sum((sale.unit_price - sale.unit_cost) * sale.quantity - sale.refunded_amount)
            FILTER (WHERE sale.unit_cost IS NOT NULL),
        0
    )::numeric(14, 2) AS profit,
    coalesce(
        sum(sale.unit_price * sale.quantity - sale.refunded_amount)
            FILTER (WHERE sale.unit_cost IS NOT NULL),
        0
    )::numeric(14, 2) AS costed_revenue
FROM sales_sale AS sale
JOIN catalog_product AS product ON product.id = sale.product_id
GROUP BY 1, 2, 3, 4, 5
WITH DATA;

CREATE UNIQUE INDEX analytics_sales_fact_key
    ON analytics_sales_fact (bucket, product_id, seller_id, payment_method);
CREATE INDEX analytics_sales_fact_seller ON analytics_sales_fact (seller_id, bucket);
CREATE INDEX analytics_sales_fact_category ON analytics_sales_fact (category_id, bucket);
"""


def create_facts(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    timezone = ZoneInfo(settings.TIME_ZONE).key
    schema_editor.execute(FACTS_SQL.format(tz=timezone))


def drop_facts(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    schema_editor.execute("DROP MATERIALIZED VIEW IF EXISTS analytics_sales_fact")


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("sales", "0001_initial"),
        ("catalog", "0002_product_search_vector"),
    ]

    operations = [migrations.RunPython(create_facts, drop_facts)]
