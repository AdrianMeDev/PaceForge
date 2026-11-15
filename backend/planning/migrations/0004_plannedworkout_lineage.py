import uuid

from django.db import migrations, models
from django.db.models import F


def own_id(apps, schema_editor):  # type: ignore[no-untyped-def]
    """A workout that exists is its own lineage: the events in the calendars of the users are keyed
    by ``paceforge-<workout id>``, and with the id as the lineage that key stays the same."""
    apps.get_model("planning", "PlannedWorkout").objects.update(lineage=F("id"))


class Migration(migrations.Migration):

    dependencies = [
        ("planning", "0003_workoutexport"),
    ]

    operations = [
        # Not added with the final default: a callable default is evaluated once for the existing
        # rows, which would give them all the same lineage.
        migrations.AddField(
            model_name="plannedworkout",
            name="lineage",
            field=models.UUIDField(editable=False, null=True),
        ),
        migrations.RunPython(own_id, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="plannedworkout",
            name="lineage",
            field=models.UUIDField(default=uuid.uuid7, editable=False),
        ),
        migrations.AddConstraint(
            model_name="plannedworkout",
            constraint=models.UniqueConstraint(
                fields=("plan", "lineage"), name="planning_one_workout_per_lineage"
            ),
        ),
    ]
