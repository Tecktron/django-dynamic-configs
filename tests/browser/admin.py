"""An admin using the zoned datetime field outside the config admin, with an inline, for the browser tests."""

from django.contrib import admin
from django.db import models

from dynamic_configs.admin import AdminZonedDateTimeWidget
from dynamic_configs.forms.datetime import ZonedDateTimeField

from .models import Event, Session

ZONED = {models.DateTimeField: {"form_class": ZonedDateTimeField, "widget": AdminZonedDateTimeWidget}}


class SessionInline(admin.TabularInline):
    model = Session
    extra = 0
    formfield_overrides = ZONED


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    inlines = [SessionInline]
    formfield_overrides = ZONED
