from django.db import migrations

from apps.content.policies import policies


# the five policies become site pages; a page that already exists (edited in the back-office) is
# never overwritten
def load_policies(apps, schema_editor):  # type: ignore[no-untyped-def]
    page_model = apps.get_model("content", "Page")
    for policy in policies():
        page_model.objects.get_or_create(
            slug=policy.slug,
            defaults={
                "title": policy.title,
                "summary": policy.summary,
                "body": policy.body,
                "version": policy.version,
                "effective_on": policy.effective_on,
                "position": 100 + policy.position,
                "is_published": True,
            },
        )


class Migration(migrations.Migration):
    dependencies = [("content", "0005_page_version")]

    operations = [migrations.RunPython(load_policies, migrations.RunPython.noop)]
