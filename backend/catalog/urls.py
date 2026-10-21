from rest_framework.routers import DefaultRouter

from .views import CategoryViewSet, ProductVariantViewSet, ProductViewSet, SupplierViewSet

router = DefaultRouter()
router.register("categories", CategoryViewSet)
router.register("suppliers", SupplierViewSet)
router.register("products", ProductViewSet)
router.register("variants", ProductVariantViewSet)

urlpatterns = router.urls
