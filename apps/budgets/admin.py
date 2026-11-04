from django.contrib import admin

from .models import BudgetItem, ExchangeRateSnapshot, Sprint, TariffProfile


class SupportAdmin(admin.ModelAdmin):
    list_per_page = 50

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(Sprint, SupportAdmin)
admin.site.register(TariffProfile, SupportAdmin)
admin.site.register(BudgetItem, SupportAdmin)
admin.site.register(ExchangeRateSnapshot, SupportAdmin)
