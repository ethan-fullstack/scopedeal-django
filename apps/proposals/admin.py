from django.contrib import admin

from .models import NegotiationNote, Proposal


class SupportAdmin(admin.ModelAdmin):
    list_per_page = 50

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(Proposal, SupportAdmin)
admin.site.register(NegotiationNote, SupportAdmin)
