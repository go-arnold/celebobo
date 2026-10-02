from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response

from apps.catalog.api.v1.backoffice_serializers import (
    AdminCategoryOutput,
    AdminProductDetailOutput,
    AdminProductFiltersInput,
    AdminProductRowOutput,
    AdminReviewOutput,
    BulkInput,
    BulkOutput,
    CategoryDeleteInput,
    CategoryFieldsSerializer,
    LowStockOutput,
    ModerateInput,
    ProductCreateInput,
    ProductPatchInput,
    ProductStatsOutput,
    ReorderInput,
    ReviewFiltersInput,
    StockAdjustmentInput,
    StockMovementOutput,
    VariantInput,
    VariantPatchInput,
)
from apps.catalog.domain.enums import ReviewStatus
from apps.catalog.domain.management import (
    BackofficeProductFilters,
    BulkProductAction,
    CategoryChanges,
    CategoryDraft,
    ProductChanges,
    ProductDraft,
    ReviewFilters,
    StockAdjustment,
    VariantChanges,
    VariantDraft,
)
from apps.catalog.facades import CategoryAdminFacade, ProductAdminFacade, ReviewModerationFacade
from apps.catalog.permissions import (
    CATEGORIES_MANAGE,
    PRODUCTS_MANAGE,
    PRODUCTS_VIEW,
    REVIEWS_MODERATE,
    STOCK_ADJUST,
)
from core.api.pagination import page_of, page_request, page_response
from core.api.views import UseCaseViewSet
from core.container import Inject

MANAGE = (PRODUCTS_MANAGE,)


class AdminProductViewSet(UseCaseViewSet):
    action_permissions = {
        "list": (PRODUCTS_VIEW,),
        "retrieve": (PRODUCTS_VIEW,),
        "create": MANAGE,
        "partial_update": MANAGE,
        "destroy": MANAGE,
        "restore": MANAGE,
        "duplicate": MANAGE,
        "bulk": MANAGE,
    }
    products = Inject(ProductAdminFacade)

    @extend_schema(parameters=[AdminProductFiltersInput], responses=page_of(AdminProductRowOutput))
    def list(self, request: Request) -> Response:
        filters = self.parse(
            AdminProductFiltersInput, into=BackofficeProductFilters, data=request.query_params
        )
        page = page_request(request, default_size=10, max_size=100)
        result = self.products.page(filters, offset=page.offset, limit=page.page_size)
        return page_response(
            request,
            page,
            total=result.total,
            results=AdminProductRowOutput(result.products, many=True).data,
            meta={"stats": ProductStatsOutput(result.stats).data},
        )

    @extend_schema(responses=AdminProductDetailOutput)
    def retrieve(self, request: Request, product_id: int) -> Response:
        return self.respond(AdminProductDetailOutput, self.products.detail(product_id))

    @extend_schema(request=ProductCreateInput, responses={201: AdminProductDetailOutput})
    def create(self, request: Request) -> Response:
        draft = self.parse(ProductCreateInput, into=ProductDraft)
        return self.respond(
            AdminProductDetailOutput, self.products.create(self.actor, draft), status=201
        )

    @extend_schema(request=ProductPatchInput, responses=AdminProductDetailOutput)
    def partial_update(self, request: Request, product_id: int) -> Response:
        changes = self.parse(ProductPatchInput, into=ProductChanges, partial=True)
        return self.respond(
            AdminProductDetailOutput, self.products.update(self.actor, product_id, changes)
        )

    @extend_schema(responses={204: None})
    def destroy(self, request: Request, product_id: int) -> Response:
        self.products.trash(self.actor, product_id)
        return Response(status=204)

    @extend_schema(request=None, responses=AdminProductDetailOutput)
    def restore(self, request: Request, product_id: int) -> Response:
        return self.respond(AdminProductDetailOutput, self.products.restore(self.actor, product_id))

    @extend_schema(request=None, responses={201: AdminProductDetailOutput})
    def duplicate(self, request: Request, product_id: int) -> Response:
        return self.respond(
            AdminProductDetailOutput, self.products.duplicate(self.actor, product_id), status=201
        )

    @extend_schema(request=BulkInput, responses=BulkOutput)
    def bulk(self, request: Request) -> Response:
        command = self.parse(BulkInput, into=BulkProductAction)
        return Response({"updated": self.products.bulk(self.actor, command)})


class AdminVariantViewSet(UseCaseViewSet):
    action_permissions = {"create": MANAGE, "partial_update": MANAGE, "destroy": MANAGE}
    products = Inject(ProductAdminFacade)

    @extend_schema(request=VariantInput, responses={201: AdminProductDetailOutput})
    def create(self, request: Request, product_id: int) -> Response:
        draft = self.parse(VariantInput, into=VariantDraft)
        return self.respond(
            AdminProductDetailOutput,
            self.products.add_variant(self.actor, product_id, draft),
            status=201,
        )

    @extend_schema(request=VariantPatchInput, responses=AdminProductDetailOutput)
    def partial_update(self, request: Request, variant_id: int) -> Response:
        changes = self.parse(VariantPatchInput, into=VariantChanges, partial=True)
        return self.respond(
            AdminProductDetailOutput, self.products.update_variant(self.actor, variant_id, changes)
        )

    @extend_schema(responses=AdminProductDetailOutput)
    def destroy(self, request: Request, variant_id: int) -> Response:
        return self.respond(
            AdminProductDetailOutput, self.products.remove_variant(self.actor, variant_id)
        )


class AdminStockViewSet(UseCaseViewSet):
    action_permissions = {
        "adjust": (STOCK_ADJUST,),
        "movements": (PRODUCTS_VIEW,),
        "alerts": (PRODUCTS_VIEW,),
    }
    products = Inject(ProductAdminFacade)

    @extend_schema(request=StockAdjustmentInput, responses={201: StockMovementOutput})
    def adjust(self, request: Request, product_id: int) -> Response:
        command = self.parse(StockAdjustmentInput, into=StockAdjustment)
        return self.respond(
            StockMovementOutput,
            self.products.adjust_stock(self.actor, product_id, command),
            status=201,
        )

    @extend_schema(responses=page_of(StockMovementOutput))
    def movements(self, request: Request, product_id: int) -> Response:
        page = page_request(request, default_size=20, max_size=100)
        movements, total = self.products.movements(
            product_id, offset=page.offset, limit=page.page_size
        )
        return page_response(
            request, page, total=total, results=StockMovementOutput(movements, many=True).data
        )

    @extend_schema(responses=LowStockOutput(many=True))
    def alerts(self, request: Request) -> Response:
        return self.respond(LowStockOutput, self.products.alerts(), many=True)


class AdminCategoryViewSet(UseCaseViewSet):
    action_permissions = dict.fromkeys(
        ("list", "create", "partial_update", "destroy", "reorder"), (CATEGORIES_MANAGE,)
    )
    categories = Inject(CategoryAdminFacade)

    @extend_schema(responses=AdminCategoryOutput(many=True))
    def list(self, request: Request) -> Response:
        return self.respond(AdminCategoryOutput, self.categories.all(), many=True)

    @extend_schema(request=CategoryFieldsSerializer, responses={201: AdminCategoryOutput})
    def create(self, request: Request) -> Response:
        draft = self.parse(CategoryFieldsSerializer, into=CategoryDraft)
        return self.respond(
            AdminCategoryOutput, self.categories.create(self.actor, draft), status=201
        )

    @extend_schema(request=CategoryFieldsSerializer, responses=AdminCategoryOutput)
    def partial_update(self, request: Request, category_id: int) -> Response:
        changes = self.parse(CategoryFieldsSerializer, into=CategoryChanges, partial=True)
        return self.respond(
            AdminCategoryOutput, self.categories.update(self.actor, category_id, changes)
        )

    @extend_schema(parameters=[CategoryDeleteInput], responses={204: None})
    def destroy(self, request: Request, category_id: int) -> Response:
        move_to = self.validated(CategoryDeleteInput, data=request.query_params).get("move_to")
        self.categories.delete(self.actor, category_id, move_to)
        return Response(status=204)

    @extend_schema(request=ReorderInput, responses=AdminCategoryOutput(many=True))
    def reorder(self, request: Request) -> Response:
        ids = self.validated(ReorderInput)["ids"]
        return self.respond(
            AdminCategoryOutput, self.categories.reorder(self.actor, ids), many=True
        )


class AdminReviewViewSet(UseCaseViewSet):
    action_permissions = {"list": (REVIEWS_MODERATE,), "partial_update": (REVIEWS_MODERATE,)}
    reviews = Inject(ReviewModerationFacade)

    @extend_schema(parameters=[ReviewFiltersInput], responses=page_of(AdminReviewOutput))
    def list(self, request: Request) -> Response:
        filters = self.parse(ReviewFiltersInput, into=ReviewFilters, data=request.query_params)
        page = page_request(request, default_size=20, max_size=100)
        reviews, total = self.reviews.page(filters, offset=page.offset, limit=page.page_size)
        return page_response(
            request, page, total=total, results=AdminReviewOutput(reviews, many=True).data
        )

    @extend_schema(request=ModerateInput, responses=AdminReviewOutput)
    def partial_update(self, request: Request, review_id: int) -> Response:
        status = ReviewStatus(self.validated(ModerateInput)["status"])
        return self.respond(AdminReviewOutput, self.reviews.moderate(self.actor, review_id, status))
