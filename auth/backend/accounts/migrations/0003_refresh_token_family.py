"""
Add RefreshToken.family.

Rows made in episode 3 have no family. Each gets a family of its own (so each
old login stays a login of one token), which keeps the new column safe to
index and means ending one family can never touch another.
"""
from django.db import migrations, models


def give_each_old_token_its_own_family(apps, schema_editor):
    RefreshToken = apps.get_model("accounts", "RefreshToken")
    for row in RefreshToken.objects.all():
        row.family = f"old{row.pk}"
        row.save(update_fields=["family"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_login_lock_refresh_token"),
    ]

    operations = [
        migrations.AddField(
            model_name="refreshtoken",
            name="family",
            field=models.CharField(db_index=True, default="", max_length=32),
            preserve_default=False,
        ),
        migrations.RunPython(give_each_old_token_its_own_family, migrations.RunPython.noop),
    ]
