from rest_framework import routers

from finance.api import views

router = routers.DefaultRouter()
router.register(
    r"invoice_payments",
    views.InvoicePaymentViewSet,
    basename="invoice_payments",
)
# router.register(r"payment_orders", views.PaymentOrderViewSet, basename="payment_orders")
urlpatterns = router.urls
