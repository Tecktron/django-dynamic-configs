"""Models for the browser tests: a page with several zoned datetimes, some in inline rows added in the browser."""

from django.db import models


class Event(models.Model):
    name = models.CharField(max_length=100)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.name


class Session(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    starts_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.event} session"
