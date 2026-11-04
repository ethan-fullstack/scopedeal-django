from django.contrib import admin

from .models import Client, SoftwareRequest


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ["name", "industry", "contact_email"]
    search_fields = ["name", "contact_email"]


@admin.register(SoftwareRequest)
class RequestAdmin(admin.ModelAdmin):
    list_display = ["title", "client", "status", "created_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
