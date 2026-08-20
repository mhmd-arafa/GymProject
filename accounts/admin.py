from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import IntakeForm, TrainerNote, User


class TrainerNoteInline(admin.TabularInline):
    model = TrainerNote
    fk_name = "client"
    extra = 1
    fields = ("body", "author")


class CustomUserAdmin(UserAdmin):
    list_display = (
        "username",
        "email",
        "phone",
        "role",
        "language",
        "is_staff",
        "is_active",
    )
    list_filter = ("role", "language", "is_staff", "is_active")

    fieldsets = UserAdmin.fieldsets + (
        ("Role Info", {"fields": ("role", "phone", "language")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Role Info", {"fields": ("role", "phone", "language")}),
    )
    inlines = [TrainerNoteInline]


@admin.register(TrainerNote)
class TrainerNoteAdmin(admin.ModelAdmin):
    list_display = ("client", "author", "created_at")
    list_filter = ("author",)
    search_fields = ("client__username", "body")


@admin.register(IntakeForm)
class IntakeFormAdmin(admin.ModelAdmin):
    list_display = (
        "client",
        "goal",
        "equipment_access",
        "training_days_per_week",
        "submitted_at",
    )
    list_filter = ("goal", "equipment_access")
    search_fields = ("client__username",)


admin.site.register(User, CustomUserAdmin)
