from django.db.models import Count, F, IntegerField, OuterRef, Prefetch, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view, inline_serializer
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from apps.audit.models import AuditLog
from apps.audit.services import AuditedViewSetMixin, log_action
from apps.common.permissions import IsAdmin, IsAdminOrReadOnly

from .filters import ArticleFilter, ArticleVariantFilter
from .importers import COLUMNS, import_articles
from .models import AgeRange, Article, ArticleVariant, Category, Color, Size, Supplier
from .serializers import (
    AgeRangeSerializer,
    ArticleSerializer,
    ArticleVariantSerializer,
    CategorySerializer,
    CategoryTreeSerializer,
    ColorSerializer,
    SizeSerializer,
    SupplierSerializer,
)


def total_quantity_subquery():
    """Somme du stock des variantes, calculée en sous-requête (insensible aux jointures des filtres)."""
    totals = (ArticleVariant.objects.filter(article=OuterRef("pk")).order_by()
              .values("article").annotate(total=Sum("quantity")).values("total"))
    return Coalesce(Subquery(totals, output_field=IntegerField()), 0)


class ReferenceViewSet(AuditedViewSetMixin, viewsets.ModelViewSet):
    """Référentiel lisible par tous, modifiable par l'administrateur, tracé dans l'audit."""

    permission_classes = [IsAdminOrReadOnly]


@extend_schema(tags=["Catalogue – référentiels"])
class CategoryViewSet(ReferenceViewSet):
    queryset = Category.objects.select_related("parent").annotate(
        article_count=Count("articles", filter=Q(articles__is_archived=False), distinct=True)
    )
    serializer_class = CategorySerializer
    filterset_fields = {"parent": ["exact", "isnull"], "is_active": ["exact"], "default_article_type": ["exact"]}
    search_fields = ["name", "description"]
    ordering_fields = ["sort_order", "name"]

    @extend_schema(summary="Arbre des catégories (principales + sous-catégories)",
                   responses=CategoryTreeSerializer(many=True))
    @action(detail=False, pagination_class=None)
    def tree(self, request):
        children = Category.objects.select_related("parent").filter(is_active=True)
        roots = (Category.objects.filter(parent__isnull=True, is_active=True)
                 .prefetch_related(Prefetch("children", queryset=children)))
        return Response(CategoryTreeSerializer(roots, many=True).data)


@extend_schema(tags=["Catalogue – référentiels"])
class AgeRangeViewSet(ReferenceViewSet):
    queryset = AgeRange.objects.all()
    serializer_class = AgeRangeSerializer
    filterset_fields = ["is_active"]
    pagination_class = None


@extend_schema(tags=["Catalogue – référentiels"])
class SizeViewSet(ReferenceViewSet):
    queryset = Size.objects.all()
    serializer_class = SizeSerializer
    filterset_fields = ["system"]
    search_fields = ["label"]
    pagination_class = None


@extend_schema(tags=["Catalogue – référentiels"])
class ColorViewSet(ReferenceViewSet):
    queryset = Color.objects.all()
    serializer_class = ColorSerializer
    search_fields = ["name"]
    pagination_class = None


@extend_schema(tags=["Catalogue – référentiels"])
class SupplierViewSet(AuditedViewSetMixin, viewsets.ModelViewSet):
    """Fournisseurs : réservés à l'administrateur (informations d'achat)."""

    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    permission_classes = [IsAdmin]
    filterset_fields = ["is_active"]
    search_fields = ["name", "contact_name", "phone", "email"]
    ordering_fields = ["name", "created_at"]


@extend_schema_view(
    list=extend_schema(summary="Liste des articles (filtres, recherche, tri)",
                       description="Les articles archivés sont exclus sauf si `is_archived=true`."),
    create=extend_schema(summary="Créer un article (avec ses variantes et son stock initial)"),
    retrieve=extend_schema(summary="Fiche article"),
    update=extend_schema(summary="Modifier un article"),
    partial_update=extend_schema(summary="Modifier partiellement un article"),
    destroy=extend_schema(summary="Supprimer un article jamais vendu ni mouvementé (sinon : archiver)"),
)
@extend_schema(tags=["Catalogue – articles"])
class ArticleViewSet(AuditedViewSetMixin, viewsets.ModelViewSet):
    serializer_class = ArticleSerializer
    permission_classes = [IsAdminOrReadOnly]
    filterset_class = ArticleFilter
    search_fields = ["name", "reference", "brand", "variants__sku", "variants__barcode"]
    ordering_fields = ["name", "reference", "sale_price", "created_at", "total_quantity"]

    def get_queryset(self):
        queryset = (
            Article.objects.select_related("category__parent", "supplier")
            .prefetch_related("age_ranges", Prefetch(
                "variants", queryset=ArticleVariant.objects.select_related("size", "color", "article")))
            .annotate(total_quantity=total_quantity_subquery())
        )
        if self.action == "list" and "is_archived" not in self.request.query_params:
            queryset = queryset.filter(is_archived=False)
        if self.request.query_params.get("search"):
            queryset = queryset.distinct()
        return queryset

    @extend_schema(summary="Archiver un article (il n'apparaît plus à la vente)", request=None,
                   responses=ArticleSerializer)
    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        article = self.get_object()
        article.is_archived, article.archived_at = True, timezone.now()
        article.save(update_fields=["is_archived", "archived_at", "updated_at"])
        log_action(AuditLog.Action.ARCHIVE, request=request, target=article)
        return Response(self.get_serializer(article).data)

    @extend_schema(summary="Désarchiver un article", request=None, responses=ArticleSerializer)
    @action(detail=True, methods=["post"])
    def restore(self, request, pk=None):
        article = self.get_object()
        article.is_archived, article.archived_at = False, None
        article.save(update_fields=["is_archived", "archived_at", "updated_at"])
        log_action(AuditLog.Action.RESTORE, request=request, target=article)
        return Response(self.get_serializer(article).data)

    @extend_schema(
        summary="Importer des articles et du stock depuis un fichier Excel ou CSV",
        description=("Fichier `.xlsx` ou `.csv` (séparateur `;` ou `,`), une ligne par variante. "
                     "Modèle : `GET /api/articles/import-template/`. Ajouter `dry_run=true` pour "
                     "vérifier le fichier sans rien enregistrer. Tout ou rien : en cas d'erreur, "
                     "aucune ligne n'est enregistrée."),
        request={"multipart/form-data": inline_serializer("ImportRequest", {
            "file": serializers.FileField(), "dry_run": serializers.BooleanField(required=False)})},
        responses=inline_serializer("ImportResult", {
            "dry_run": serializers.BooleanField(), "success": serializers.BooleanField(),
            "rows": serializers.IntegerField(), "errors": serializers.ListField(child=serializers.DictField()),
            "articles_created": serializers.IntegerField(), "articles_updated": serializers.IntegerField(),
            "variants_created": serializers.IntegerField(), "units_added": serializers.IntegerField()}),
    )
    @action(detail=False, methods=["post"], url_path="import", permission_classes=[IsAdmin],
            parser_classes=[MultiPartParser, FormParser])
    def import_file(self, request):
        uploaded = request.FILES.get("file")
        if uploaded is None:
            return Response({"file": ["Aucun fichier envoyé."]}, status=status.HTTP_400_BAD_REQUEST)
        dry_run = str(request.data.get("dry_run", "")).lower() in ("1", "true", "oui")
        result = import_articles(uploaded, request.user, dry_run=dry_run)
        if result["success"] and not dry_run:
            log_action(AuditLog.Action.STOCK_IMPORT, request=request,
                       details={"fichier": uploaded.name, **{k: v for k, v in result.items() if k != "errors"}})
        return Response(result, status=status.HTTP_200_OK if result["success"] else status.HTTP_400_BAD_REQUEST)

    @extend_schema(summary="Télécharger le modèle de fichier d'import (CSV)", responses={(200, "text/csv"): bytes})
    @action(detail=False, url_path="import-template", permission_classes=[IsAdmin])
    def import_template(self, request):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="modele-import-articles.csv"'
        response.write("﻿")
        response.write(";".join(c for c, _, _ in COLUMNS) + "\n")
        response.write(";".join(example for _, _, example in COLUMNS) + "\n")
        return response


@extend_schema_view(
    list=extend_schema(summary="Liste des variantes (taille × couleur) avec leur stock"),
    create=extend_schema(summary="Ajouter une variante à un article (stock à 0, utiliser une entrée de stock ensuite)"),
)
@extend_schema(tags=["Catalogue – articles"])
class ArticleVariantViewSet(AuditedViewSetMixin, viewsets.ModelViewSet):
    serializer_class = ArticleVariantSerializer
    permission_classes = [IsAdminOrReadOnly]
    filterset_class = ArticleVariantFilter
    search_fields = ["sku", "barcode", "article__name", "article__reference", "color__name", "size__label"]
    ordering_fields = ["quantity", "sku", "article__name", "created_at"]

    def get_queryset(self):
        queryset = ArticleVariant.objects.select_related("article", "size", "color")
        if self.action in ("list", "low_stock") and self.request.query_params.get("include_archived") != "true":
            queryset = queryset.filter(article__is_archived=False)
        return queryset

    @extend_schema(
        summary="Retrouver une variante par code-barres ou SKU (douchette / caisse)",
        parameters=[OpenApiParameter("code", str, required=True, description="Code-barres ou SKU scanné")],
        responses=ArticleVariantSerializer,
    )
    @action(detail=False)
    def lookup(self, request):
        code = request.query_params.get("code", "").strip()
        variant = (ArticleVariant.objects.select_related("article", "size", "color")
                   .filter(Q(barcode=code) | Q(sku__iexact=code)).first() if code else None)
        if variant is None:
            return Response({"detail": "Aucun article ne correspond à ce code."}, status=status.HTTP_404_NOT_FOUND)
        return Response(self.get_serializer(variant).data)

    @extend_schema(summary="Variantes en stock faible ou en rupture")
    @action(detail=False, url_path="low-stock")
    def low_stock(self, request):
        queryset = self.filter_queryset(self.get_queryset()).filter(
            is_active=True, quantity__lte=F("alert_threshold")).order_by("quantity")
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)
