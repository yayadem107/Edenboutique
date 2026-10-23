from rest_framework.routers import DefaultRouter

from .views import CashReportViewSet, SaleViewSet

router = DefaultRouter()
router.register("sales", SaleViewSet, basename="sale")
router.register("cash-reports", CashReportViewSet, basename="cash-report")

urlpatterns = router.urls
