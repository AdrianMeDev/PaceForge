from rest_framework import serializers

from .models import Activity

SUMMARY_FIELDS = [
    "id",
    "source",
    "sport",
    "source_sport",
    "start_time",
    "elapsed_seconds",
    "timer_seconds",
    "distance_m",
    "avg_heart_rate",
    "max_heart_rate",
    "avg_power_w",
    "total_ascent_m",
    "calories",
    "manufacturer",
    "created_at",
]


class ActivitySerializer(serializers.ModelSerializer[Activity]):
    """The summary of an activity. Neither the owner, the file hash nor the file itself is part of
    it: the file holds the whole GPS track and is never returned."""

    class Meta:
        model = Activity
        fields = SUMMARY_FIELDS
        read_only_fields = fields


class ActivityDetailSerializer(ActivitySerializer):
    class Meta(ActivitySerializer.Meta):
        fields = [*SUMMARY_FIELDS, "laps"]
        read_only_fields = fields
