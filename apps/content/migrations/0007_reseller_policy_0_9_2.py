import hashlib

from django.db import migrations

from apps.content.policies import POLICY_DIR, read

SLUG = "politique-revendeurs"
# sha256 of the 0.9.1 body loaded by 0006: only that untouched text is replaced, a page edited in
# the back-office is left for the staff to update
LOADED_0_9_1 = "44291d6aa3977d82e5f7599de010bf028e2b621b70f796305ce324be8ee6fed0"


# version 0.9.2 aligns the commissions with the owner's rules (50 % of the margin, nothing on an
# order paid even partly with points or a coupon)
def update_reseller_policy(apps, schema_editor):  # type: ignore[no-untyped-def]
    page_model = apps.get_model("content", "Page")
    page = page_model.objects.filter(slug=SLUG, version="0.9.1").first()
    if page is None or hashlib.sha256(page.body.encode()).hexdigest() != LOADED_0_9_1:
        return
    policy = read(POLICY_DIR / f"{SLUG}.md")
    page.body, page.version, page.effective_on = policy.body, policy.version, policy.effective_on
    page.summary = policy.summary
    page.save(update_fields=["body", "version", "effective_on", "summary"])


class Migration(migrations.Migration):
    dependencies = [("content", "0006_load_policies")]

    operations = [migrations.RunPython(update_reseller_policy, migrations.RunPython.noop)]
