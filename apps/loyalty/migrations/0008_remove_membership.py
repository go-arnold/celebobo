# Celebobo Plus (the paid membership) is dropped: no member was ever enrolled in production,
# so its tables and settings go without a data migration. The fidelity points stay.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('loyalty', '0007_points_closing'),
    ]

    operations = [
        migrations.DeleteModel(name='MembershipRequest'),
        migrations.DeleteModel(name='Membership'),
        migrations.RemoveField(model_name='loyaltysettings', name='membership_enabled'),
        migrations.RemoveField(model_name='loyaltysettings', name='membership_monthly_price'),
        migrations.RemoveField(model_name='loyaltysettings', name='membership_yearly_price'),
        migrations.RemoveField(model_name='loyaltysettings', name='membership_trial_days'),
        migrations.RemoveField(model_name='loyaltysettings', name='membership_reminder_days'),
    ]
