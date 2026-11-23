from django.contrib import admin

from apps.cash.models import CashCollection, CashRemittance


@admin.register(CashCollection)
class CashCollectionAdmin(admin.ModelAdmin[CashCollection]):
    list_display = ("order_number", "reseller", "amount", "covered", "due_at", "voided_at")
    raw_id_fields = ("reseller", "order")


@admin.register(CashRemittance)
class CashRemittanceAdmin(admin.ModelAdmin[CashRemittance]):
    list_display = ("reseller", "amount", "reference", "received_at", "recorded_by")
    raw_id_fields = ("reseller", "recorded_by")
