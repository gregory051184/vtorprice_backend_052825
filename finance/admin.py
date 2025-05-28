# Register your models here.
from django.contrib import admin

from finance.models import InvoicePayment, PaymentOrder


@admin.register(InvoicePayment)
class InvoicePaymentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "amount",
        "status",
        "company",
        "is_deleted",
        "created_at",
    )
    list_filter = ("status", "company", "is_deleted")
    search_fields = ("id", "company__name")
    readonly_fields = ("created_at",)
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "amount",
                    "status",
                    "company",
                    "object_id",
                    "content_type",
                    "created_at",
                )
            },
        ),
    )


@admin.register(PaymentOrder)
class PaymentOrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "document",
        "get_payment_order_company",
        "type",
        "total",
        "is_deleted",
        "created_at",
    )
    list_filter = ("type", "invoice_payment__company", "is_deleted")
    search_fields = ("id", "invoice_payment__company__name")
    readonly_fields = ("created_at",)
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "document",
                    "total",
                    "type",
                    "created_at",
                    "invoice_payment",
                )
            },
        ),
    )

    def get_payment_order_company(self, obj: PaymentOrder):
        return obj.invoice_payment.company
