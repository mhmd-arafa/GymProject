from django.contrib import admin

from .models import BodyMeasurement, CheckIn, ProgressPhoto


class ProgressPhotoInline(admin.TabularInline):
    model = ProgressPhoto
    fk_name = "checkin"
    extra = 0
    fields = ("pose", "image", "date", "consent_public")
    readonly_fields = ("consent_given_at",)


@admin.register(BodyMeasurement)
class BodyMeasurementAdmin(admin.ModelAdmin):
    list_display = ("client", "date", "weight_kg", "waist_cm", "chest_cm", "arm_cm")
    list_filter = ("client",)
    date_hierarchy = "date"


@admin.register(ProgressPhoto)
class ProgressPhotoAdmin(admin.ModelAdmin):
    list_display = ("client", "date", "pose", "checkin", "consent_public", "consent_given_at")
    list_filter = ("consent_public", "pose", "client")
    date_hierarchy = "date"
    readonly_fields = ("consent_given_at", "uploaded_at")


@admin.register(CheckIn)
class CheckInAdmin(admin.ModelAdmin):
    list_display = (
        "client",
        "due_date",
        "submitted_at",
        "weight_kg",
        "adherence_rating",
        "reviewed",
    )
    list_filter = ("reviewed", "client")
    date_hierarchy = "due_date"
    inlines = [ProgressPhotoInline]
