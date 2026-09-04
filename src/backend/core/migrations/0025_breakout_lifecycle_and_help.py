import uuid

import django.db.models.deletion
from django.db import migrations, models


def backfill_assignment_sessions(apps, schema_editor):
    """Copy each assignment's room session into the direct session key."""
    assignment_model = apps.get_model("core", "BreakoutAssignment")
    for assignment in assignment_model.objects.select_related("breakout_room").all():
        assignment.session_id = assignment.breakout_room.session_id
        assignment.save(update_fields=["session"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0024_breakout_assignment_identity_index"),
    ]

    operations = [
        migrations.AddField(
            model_name="breakoutassignment",
            name="session",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="assignments",
                to="core.breakoutsession",
                verbose_name="breakout session",
            ),
        ),
        migrations.RunPython(
            backfill_assignment_sessions,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="breakoutassignment",
            name="session",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="assignments",
                to="core.breakoutsession",
                verbose_name="breakout session",
            ),
        ),
        migrations.AddConstraint(
            model_name="breakoutassignment",
            constraint=models.UniqueConstraint(
                fields=("session", "participant_identity"),
                name="one_breakout_assignment_per_participant",
            ),
        ),
        migrations.AlterField(
            model_name="breakoutassignment",
            name="participant_identity",
            field=models.CharField(
                db_index=True,
                help_text="Server-issued LiveKit participant identity.",
                max_length=255,
                verbose_name="participant identity",
            ),
        ),
        migrations.AddField(
            model_name="breakoutsession",
            name="effect_error",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Latest retryable LiveKit reconciliation error.",
                verbose_name="effect error",
            ),
        ),
        migrations.AddField(
            model_name="breakoutsession",
            name="ends_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Absolute timer boundary for a timed breakout session.",
                null=True,
                verbose_name="ends at",
            ),
        ),
        migrations.AddField(
            model_name="breakoutsession",
            name="revision",
            field=models.PositiveBigIntegerField(
                default=0,
                help_text="Monotonic revision for participant-visible session changes.",
                verbose_name="revision",
            ),
        ),
        migrations.AlterField(
            model_name="breakoutsession",
            name="status",
            field=models.CharField(
                choices=[
                    ("configuring", "Configuring"),
                    ("activating", "Activating"),
                    ("active", "Active"),
                    ("closing", "Closing"),
                    ("closed", "Closed"),
                ],
                default="configuring",
                max_length=20,
                verbose_name="session status",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="breakoutsession",
            name="one_active_session_per_room",
        ),
        migrations.AddConstraint(
            model_name="breakoutsession",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    status__in=["configuring", "activating", "active", "closing"]
                ),
                fields=("room",),
                name="one_active_session_per_room",
            ),
        ),
        migrations.CreateModel(
            name="BreakoutHelpRequest",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        help_text="primary key for the record as UUID",
                        primary_key=True,
                        serialize=False,
                        verbose_name="id",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        help_text="date and time at which a record was created",
                        verbose_name="created on",
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True,
                        help_text="date and time at which a record was last updated",
                        verbose_name="updated on",
                    ),
                ),
                ("requester_identity", models.CharField(db_index=True, max_length=255)),
                (
                    "requester_name",
                    models.CharField(blank=True, default="", max_length=255),
                ),
                ("assignment_revision", models.PositiveBigIntegerField(default=0)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("open", "Open"),
                            ("cancelled", "Cancelled"),
                            ("acknowledged", "Acknowledged"),
                        ],
                        default="open",
                        max_length=20,
                    ),
                ),
                ("cancelled_at", models.DateTimeField(blank=True, null=True)),
                ("acknowledged_at", models.DateTimeField(blank=True, null=True)),
                (
                    "breakout_room",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="help_requests",
                        to="core.breakoutroom",
                        verbose_name="breakout room",
                    ),
                ),
                (
                    "session",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="help_requests",
                        to="core.breakoutsession",
                        verbose_name="breakout session",
                    ),
                ),
            ],
            options={
                "db_table": "meet_breakout_help_request",
                "ordering": ("created_at",),
            },
        ),
        migrations.AddConstraint(
            model_name="breakouthelprequest",
            constraint=models.UniqueConstraint(
                condition=models.Q(status="open"),
                fields=("session", "requester_identity"),
                name="one_open_help_request_per_participant",
            ),
        ),
    ]
