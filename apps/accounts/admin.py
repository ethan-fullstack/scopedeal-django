from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class AccountAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("ScopeDeal", {"fields": ("role", "client")}),)
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("ScopeDeal", {"fields": ("email", "role", "client")}),
    )
    list_display = ["username", "email", "role", "client", "is_staff"]
