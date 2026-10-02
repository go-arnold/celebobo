from django.db import models

FACTS_VIEW = "analytics_sales_fact"


class SalesFact(models.Model):
    pk = models.CompositePrimaryKey("bucket", "product_id", "seller_id", "payment_method")
    bucket = models.DateTimeField()
    product_id = models.BigIntegerField()
    category_id = models.BigIntegerField()
    seller_id = models.BigIntegerField()
    payment_method = models.CharField(max_length=24)
    sales_count = models.IntegerField()
    units = models.IntegerField()
    revenue = models.DecimalField(max_digits=14, decimal_places=2)
    profit = models.DecimalField(max_digits=14, decimal_places=2)
    costed_revenue = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        managed = False
        db_table = FACTS_VIEW

    def __str__(self) -> str:
        return f"{self.bucket:%Y-%m-%d %H}h · produit {self.product_id}"
