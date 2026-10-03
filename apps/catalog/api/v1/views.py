from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from apps.catalog.api.v1.serializers import (
    CategoryOutput,
    FacetsOutput,
    FavoriteInput,
    ProductCardOutput,
    ProductDetailOutput,
    ProductQueryInput,
    ReviewEligibilityOutput,
    ReviewInput,
    ReviewOutput,
    ReviewSummaryOutput,
    SuggestionOutput,
)
from apps.catalog.domain.queries import PostReview, ProductQuery
from apps.catalog.facades import CatalogFacade, FavoriteFacade, ReviewFacade
from apps.catalog.permissions import FAVORITES_MANAGE, REVIEWS_CREATE
from core.api.caching import public_cache
from core.api.pagination import PageRequest, page_of, page_request, page_response
from core.api.views import UseCaseViewSet
from core.container import Inject

SEARCH_PARAMETER = OpenApiParameter("q", str, description="Texte recherché (2 caractères min.)")


class CategoryViewSet(UseCaseViewSet):
    permission_classes = (AllowAny,)
    lookup_field = "slug"
    lookup_value_converter = "slug"
    catalog = Inject(CatalogFacade)

    @extend_schema(responses=CategoryOutput(many=True))
    @public_cache
    def list(self, request: Request) -> Response:
        return self.respond(CategoryOutput, self.catalog.categories(), many=True)

    @extend_schema(responses=CategoryOutput)
    @public_cache
    def retrieve(self, request: Request, slug: str) -> Response:
        return self.respond(CategoryOutput, self.catalog.category(slug))


class ProductViewSet(UseCaseViewSet):
    permission_classes = (AllowAny,)
    lookup_field = "slug"
    lookup_value_converter = "slug"
    catalog = Inject(CatalogFacade)

    @extend_schema(parameters=[ProductQueryInput], responses=page_of(ProductCardOutput))
    def list(self, request: Request) -> Response:
        query = self._query()
        page = self.catalog.browse(self.actor, query)
        return page_response(
            request,
            PageRequest(page=query.page, page_size=query.page_size),
            total=page.total,
            results=ProductCardOutput(page.cards, many=True).data,
        )

    @extend_schema(parameters=[ProductQueryInput], responses=FacetsOutput)
    @action(detail=False, methods=["get"])
    def facets(self, request: Request) -> Response:
        return self.respond(FacetsOutput, self.catalog.facets(self._query()))

    @extend_schema(responses=ProductDetailOutput)
    def retrieve(self, request: Request, slug: str) -> Response:
        return self.respond(ProductDetailOutput, self.catalog.product(self.actor, slug))

    @extend_schema(responses=page_of(ProductCardOutput))
    @action(detail=True, methods=["get"])
    def related(self, request: Request, slug: str) -> Response:
        return self.respond(ProductCardOutput, self.catalog.related(self.actor, slug), many=True)

    def _query(self) -> ProductQuery:
        return self.parse(ProductQueryInput, into=ProductQuery, data=self.request.query_params)


class SuggestViewSet(UseCaseViewSet):
    permission_classes = (AllowAny,)
    throttle_scope = "search"
    catalog = Inject(CatalogFacade)

    @extend_schema(parameters=[SEARCH_PARAMETER], responses=SuggestionOutput(many=True))
    def list(self, request: Request) -> Response:
        suggestions = self.catalog.suggest(str(request.query_params.get("q", "")))
        return self.respond(SuggestionOutput, suggestions, many=True)


class ReviewViewSet(UseCaseViewSet):
    action_permissions = {"create": (REVIEWS_CREATE,)}
    permission_classes = (AllowAny,)
    reviews = Inject(ReviewFacade)

    @extend_schema(responses=page_of(ReviewOutput))
    def list(self, request: Request, slug: str) -> Response:
        page = page_request(request, default_size=10, max_size=50)
        result = self.reviews.page(slug, offset=page.offset, limit=page.page_size)
        return page_response(
            request,
            page,
            total=result.total,
            results=ReviewOutput(result.reviews, many=True).data,
            meta={"summary": ReviewSummaryOutput(result.summary).data},
        )

    @extend_schema(request=ReviewInput, responses={201: ReviewOutput, 200: ReviewOutput})
    def create(self, request: Request, slug: str) -> Response:
        command = self.parse(ReviewInput, into=PostReview)
        review, created = self.reviews.post(self.actor, slug, command)
        return self.respond(ReviewOutput, review, status=201 if created else 200)

    @extend_schema(responses=ReviewEligibilityOutput)
    @action(detail=False, methods=["get"])
    def eligibility(self, request: Request, slug: str) -> Response:
        return self.respond(ReviewEligibilityOutput, self.reviews.eligibility(self.actor, slug))


class FavoriteViewSet(UseCaseViewSet):
    action_permissions = dict.fromkeys(("list", "create", "destroy"), (FAVORITES_MANAGE,))
    favorites = Inject(FavoriteFacade)

    @extend_schema(responses=ProductCardOutput(many=True))
    def list(self, request: Request) -> Response:
        page = page_request(request, default_size=12, max_size=48)
        result = self.favorites.page(self.actor, offset=page.offset, limit=page.page_size)
        return page_response(
            request,
            page,
            total=result.total,
            results=ProductCardOutput(result.cards, many=True).data,
        )

    @extend_schema(request=FavoriteInput, responses={201: ProductCardOutput})
    def create(self, request: Request) -> Response:
        product_id = self.validated(FavoriteInput)["product_id"]
        return self.respond(
            ProductCardOutput, self.favorites.add(self.actor, product_id), status=201
        )

    @extend_schema(responses={204: None})
    def destroy(self, request: Request, product_id: int) -> Response:
        self.favorites.remove(self.actor, product_id)
        return Response(status=204)
