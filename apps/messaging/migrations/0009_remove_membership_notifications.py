# The paid membership is dropped: its notification kinds go, with any notification of those kinds.

from django.apps.registry import Apps
from django.db import migrations, models
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

MEMBERSHIP_KINDS = (
    'membership_requested',
    'membership_started',
    'membership_rejected',
    'membership_ending',
)


def delete_membership_notifications(apps: Apps, _schema_editor: BaseDatabaseSchemaEditor) -> None:
    apps.get_model('messaging', 'Notification').objects.filter(kind__in=MEMBERSHIP_KINDS).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('messaging', '0008_delivery_attempts'),
    ]

    operations = [
        migrations.RunPython(delete_membership_notifications, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='notification',
            name='kind',
            field=models.CharField(choices=[('order_placed', 'order_placed'), ('order_assigned', 'order_assigned'), ('assignment_declined', 'assignment_declined'), ('order_status', 'order_status'), ('new_message', 'new_message'), ('support_request', 'support_request'), ('conversation_assigned', 'conversation_assigned'), ('price_proposed', 'price_proposed'), ('price_answered', 'price_answered'), ('shipping_quoted', 'shipping_quoted'), ('shipping_answered', 'shipping_answered'), ('refund_due', 'refund_due'), ('order_refunded', 'order_refunded'), ('delivery_code', 'delivery_code'), ('delivery_code_locked', 'delivery_code_locked'), ('reseller_rated', 'reseller_rated'), ('delivery_attempt', 'delivery_attempt')], max_length=24),
        ),
    ]
