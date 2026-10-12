"""Administration Django de l'application DataZen."""
from django.contrib import admin

from .models import CleaningRule, DataFile, Profile


@admin.register(DataFile)
class DataFileAdmin(admin.ModelAdmin):
    list_display = ("original_name", "owner", "status", "progress", "created_at")
    list_filter = ("status", "created_at", "owner")
    search_fields = ("original_name",)
    readonly_fields = ("original_name", "cleaned_file", "created_at", "updated_at")


@admin.register(CleaningRule)
class CleaningRuleAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "operation", "column", "is_active", "created_at")
    list_filter = ("operation", "is_active", "owner")
    search_fields = ("name", "column")


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "has_avatar", "updated_at")
    search_fields = ("user__username", "user__email", "user__first_name", "user__last_name")
    readonly_fields = ("created_at", "updated_at")

    @admin.display(boolean=True, description="Photo")
    def has_avatar(self, obj):
        return bool(obj.avatar)
