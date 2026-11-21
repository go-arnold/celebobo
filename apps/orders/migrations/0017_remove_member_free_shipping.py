# Free shipping for Celebobo Plus members goes with the paid membership.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0016_points'),
    ]

    operations = [
        migrations.RemoveField(model_name='shippingzone', name='member_free_shipping'),
    ]
