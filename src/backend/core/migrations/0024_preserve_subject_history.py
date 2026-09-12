"""Record subject validation changes without rewriting migration history."""

import core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0023_breakout_rooms'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='sub',
            field=models.CharField(blank=True, help_text='Optional for pending users; required upon account activation. 255 characters or fewer. Printable ASCII characters only.', max_length=255, null=True, unique=True, validators=[core.validators.sub_validator], verbose_name='sub'),
        ),
    ]
