from django.contrib import admin
from .models import ProgressLog


@admin.register(ProgressLog)
class ProgressLogAdmin(admin.ModelAdmin):
    list_display = ("client", "weight", "date", "created_at")
    list_filter = ("client", "date")
    search_fields = ("client__username", "client__email", "notes")
    date_hierarchy = "date"
