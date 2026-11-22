from django.db import migrations

from apps.content.policies import POLICY_DIR, read

SLUG = "conditions-de-vente"


# the conditions of sale become a versioned page, like the five policies (0006); a page that
# already exists (edited in the back-office) is never overwritten
def load_conditions(apps, schema_editor):  # type: ignore[no-untyped-def]
    page_model = apps.get_model("content", "Page")
    policy = read(POLICY_DIR / f"{SLUG}.md")
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
    dependencies = [("content", "0007_reseller_policy_0_9_2")]

    operations = [migrations.RunPython(load_conditions, migrations.RunPython.noop)]
