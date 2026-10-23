from rest_framework.routers import DefaultRouter

from .views import (
    AgeRangeViewSet,
    ArticleVariantViewSet,
    ArticleViewSet,
    CategoryViewSet,
    ColorViewSet,
    SizeViewSet,
    SupplierViewSet,
)

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("age-ranges", AgeRangeViewSet, basename="age-range")
router.register("sizes", SizeViewSet, basename="size")
router.register("colors", ColorViewSet, basename="color")
router.register("suppliers", SupplierViewSet, basename="supplier")
router.register("articles", ArticleViewSet, basename="article")
router.register("variants", ArticleVariantViewSet, basename="variant")

urlpatterns = router.urls
