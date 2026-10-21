from rest_framework.routers import DefaultRouter

from .views import StockMovementViewSet

router = DefaultRouter()
router.register("movements", StockMovementViewSet)

urlpatterns = router.urls
