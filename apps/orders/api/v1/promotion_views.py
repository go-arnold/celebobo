from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from apps.orders.api.v1.promotion_serializers import (
    CouponFiltersInput,
    CouponInput,
    CouponOutput,
    ZoneInput,
    ZoneOutput,
)
from apps.orders.domain.commands import CouponChanges, CouponFields, ZoneChanges, ZoneFields
from apps.orders.facades import PromotionFacade
from apps.orders.permissions import COUPONS_MANAGE, SHIPPING_MANAGE
from core.api.pagination import page_of, page_request, page_response
from core.api.views import UseCaseViewSet
from core.container import Inject


class ShippingZonePublicViewSet(UseCaseViewSet):
    permission_classes = (AllowAny,)
    promotions = Inject(PromotionFacade)

    @extend_schema(responses=ZoneOutput(many=True))
    def list(self, request: Request) -> Response:
        return self.respond(ZoneOutput, self.promotions.shipping_zones(active_only=True), many=True)


class ShippingZoneAdminViewSet(UseCaseViewSet):
    action_permissions = dict.fromkeys(
        ("list", "create", "partial_update", "destroy"), (SHIPPING_MANAGE,)
    )
    promotions = Inject(PromotionFacade)

    @extend_schema(responses=ZoneOutput(many=True))
    def list(self, request: Request) -> Response:
        return self.respond(
            ZoneOutput, self.promotions.shipping_zones(active_only=False), many=True
        )

    @extend_schema(request=ZoneInput, responses={201: ZoneOutput})
    def create(self, request: Request) -> Response:
        zone = self.promotions.create_zone(self.parse(ZoneInput, into=ZoneFields))
        return self.respond(ZoneOutput, zone, status=201)

    @extend_schema(request=ZoneInput, responses=ZoneOutput)
    def partial_update(self, request: Request, zone_id: int) -> Response:
        changes = self.parse(ZoneInput, into=ZoneChanges, partial=True)
        return self.respond(ZoneOutput, self.promotions.update_zone(zone_id, changes))

    @extend_schema(responses={204: None})
    def destroy(self, request: Request, zone_id: int) -> Response:
        self.promotions.delete_zone(zone_id)
        return Response(status=204)


class CouponAdminViewSet(UseCaseViewSet):
    action_permissions = dict.fromkeys(
        ("list", "create", "retrieve", "partial_update", "destroy"), (COUPONS_MANAGE,)
    )
    promotions = Inject(PromotionFacade)

    @extend_schema(parameters=[CouponFiltersInput], responses=page_of(CouponOutput))
    def list(self, request: Request) -> Response:
        filters = self.validated(CouponFiltersInput, data=request.query_params)
        page = page_request(request, default_size=20, max_size=100)
        coupons, total = self.promotions.coupons(
            search=filters.get("search"),
            active=filters["active"],
            offset=page.offset,
            limit=page.page_size,
        )
        return page_response(
            request, page, total=total, results=CouponOutput(coupons, many=True).data
        )

    @extend_schema(request=CouponInput, responses={201: CouponOutput})
    def create(self, request: Request) -> Response:
        coupon = self.promotions.create_coupon(self.parse(CouponInput, into=CouponFields))
        return self.respond(CouponOutput, coupon, status=201)

    @extend_schema(responses=CouponOutput)
    def retrieve(self, request: Request, coupon_id: int) -> Response:
        return self.respond(CouponOutput, self.promotions.coupon(coupon_id))

    @extend_schema(request=CouponInput, responses=CouponOutput)
    def partial_update(self, request: Request, coupon_id: int) -> Response:
        changes = self.parse(CouponInput, into=CouponChanges, partial=True)
        return self.respond(CouponOutput, self.promotions.update_coupon(coupon_id, changes))

    @extend_schema(responses=CouponOutput)
    def destroy(self, request: Request, coupon_id: int) -> Response:
        return self.respond(CouponOutput, self.promotions.deactivate_coupon(coupon_id))
