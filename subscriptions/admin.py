from django.contrib import admin
from .models import Subscription


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("client", "plan_type", "status", "start_date", "end_date", "created_at")
    list_filter = ("status", "plan_type", "created_at")
    search_fields = ("client__username", "client__email", "notes")
    date_hierarchy = "created_at"
