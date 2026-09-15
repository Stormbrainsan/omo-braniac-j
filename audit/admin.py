from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("event", "email", "ip_address", "created_at")
    list_filter = ("event",)
    search_fields = ("email", "ip_address")
    ordering = ("-created_at",)
    readonly_fields = [f.name for f in AuditLog._meta.fields]
