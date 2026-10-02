from uuid import UUID

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import BaseThrottle

from apps.orders.api.v1.serializers import (
    AssignableResellerOutput,
    AssignInput,
    CancelInput,
    CartContextInput,
    CartItemInput,
    CartMergeInput,
    CartOutput,
    CartQuantityInput,
    ClientOrderDetailOutput,
    ClientStatusInput,
    CouponCodeInput,
    DeclineInput,
    OrderDetailOutput,
    OrderFiltersInput,
    OrderSummaryOutput,
    PlaceOrderInput,
    QuoteOutput,
    QuoteRequestInput,
    TrackingOutput,
    TrackInput,
    TransitionInput,
)
from apps.orders.domain.commands import (
    AssignOrder,
    CancelOrder,
    DeclineAssignment,
    OrderFilters,
    PlaceOrder,
    TrackOrder,
    TransitionOrder,
)
from apps.orders.domain.enums import OrderStatus
from apps.orders.facades import CartFacade, CheckoutFacade, ClientOrderFacade, DispatchFacade
from apps.orders.permissions import (
    ORDERS_ASSIGN,
    ORDERS_ASSIGNMENT_DECLINE,
    ORDERS_CANCEL_MINE,
    ORDERS_PLACE,
    ORDERS_STATUS_ADVANCE,
    ORDERS_VIEW_ASSIGNED,
    ORDERS_VIEW_MINE,
)
from core.api.idempotency import idempotent
from core.api.pagination import page_of, page_request, page_response
from core.api.views import UseCaseViewSet
from core.container import Inject
from core.domain.errors import ValidationFailed

CART_HEADER = "X-Cart-Token"
CART_PARAMETER = OpenApiParameter(CART_HEADER, str, OpenApiParameter.HEADER, required=False)


class CartViewSet(UseCaseViewSet):
    permission_classes = (AllowAny,)
    carts = Inject(CartFacade)

    def get_throttles(self) -> list[BaseThrottle]:
        self.throttle_scope = "coupons" if getattr(self, "action", None) == "apply_coupon" else ""
        return list(super().get_throttles())

    @extend_schema(parameters=[CART_PARAMETER, CartContextInput], responses=CartOutput)
    def retrieve(self, request: Request) -> Response:
        city = self.validated(CartContextInput, data=request.query_params).get("city")
        return self.respond(CartOutput, self.carts.view(self.actor, self._token(), city=city))

    @extend_schema(parameters=[CART_PARAMETER], request=CouponCodeInput, responses=CartOutput)
    def apply_coupon(self, request: Request) -> Response:
        code = self.validated(CouponCodeInput)["code"]
        return self.respond(CartOutput, self.carts.apply_coupon(self.actor, self._token(), code))

    @extend_schema(parameters=[CART_PARAMETER], responses=CartOutput)
    def remove_coupon(self, request: Request) -> Response:
        return self.respond(CartOutput, self.carts.remove_coupon(self.actor, self._token()))

    @extend_schema(parameters=[CART_PARAMETER], request=CartItemInput, responses={201: CartOutput})
    def create(self, request: Request) -> Response:
        line = self.validated(CartItemInput)
        cart = self.carts.add(self.actor, self._token(), line)
        return self.respond(CartOutput, cart, status=201)

    @extend_schema(parameters=[CART_PARAMETER], request=CartQuantityInput, responses=CartOutput)
    def partial_update(self, request: Request, item_id: int) -> Response:
        quantity = self.validated(CartQuantityInput)["quantity"]
        cart = self.carts.update(self.actor, self._token(), item_id, quantity)
        return self.respond(CartOutput, cart)

    @extend_schema(parameters=[CART_PARAMETER], responses=CartOutput)
    def destroy_item(self, request: Request, item_id: int) -> Response:
        return self.respond(CartOutput, self.carts.remove(self.actor, self._token(), item_id))

    @extend_schema(parameters=[CART_PARAMETER], responses={204: None})
    def destroy(self, request: Request) -> Response:
        self.carts.clear(self.actor, self._token())
        return Response(status=204)

    def _token(self) -> UUID | None:
        raw = self.request.headers.get(CART_HEADER)
        if not raw:
            return None
        try:
            return UUID(raw)
        except ValueError as exc:
            raise ValidationFailed(errors={CART_HEADER: ["Jeton de panier invalide."]}) from exc


class CartMergeViewSet(UseCaseViewSet):
    carts = Inject(CartFacade)

    @extend_schema(request=CartMergeInput, responses=CartOutput)
    def create(self, request: Request) -> Response:
        token = self.validated(CartMergeInput)["token"]
        return self.respond(CartOutput, self.carts.merge(self.actor, token))


class QuoteViewSet(UseCaseViewSet):
    permission_classes = (AllowAny,)
    checkout = Inject(CheckoutFacade)

    @extend_schema(request=QuoteRequestInput, responses=QuoteOutput)
    def create(self, request: Request) -> Response:
        data = self.validated(QuoteRequestInput)
        quote = self.checkout.quote(
            self.actor,
            data["lines"],
            city=data.get("city") or None,
            coupon_code=data.get("coupon_code") or None,
        )
        return self.respond(QuoteOutput, quote)


class CheckoutViewSet(UseCaseViewSet):
    action_permissions = {"create": (ORDERS_PLACE,)}
    checkout = Inject(CheckoutFacade)

    @extend_schema(request=PlaceOrderInput, responses={201: ClientOrderDetailOutput})
    @idempotent()
    def create(self, request: Request) -> Response:
        command = self.parse(PlaceOrderInput, into=PlaceOrder)
        order = self.checkout.place(self.actor, command)
        return self.respond(ClientOrderDetailOutput, order, status=201)


class TrackingViewSet(UseCaseViewSet):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_scope = "tracking"
    orders = Inject(ClientOrderFacade)

    @extend_schema(request=TrackInput, responses=TrackingOutput)
    def create(self, request: Request) -> Response:
        return self.respond(
            TrackingOutput, self.orders.track(self.parse(TrackInput, into=TrackOrder))
        )


class ClientOrderViewSet(UseCaseViewSet):
    action_permissions = {
        "list": (ORDERS_VIEW_MINE,),
        "retrieve": (ORDERS_VIEW_MINE,),
        "cancel": (ORDERS_CANCEL_MINE,),
    }
    orders = Inject(ClientOrderFacade)

    @extend_schema(parameters=[ClientStatusInput], responses=page_of(OrderSummaryOutput))
    def list(self, request: Request) -> Response:
        status = self.validated(ClientStatusInput, data=request.query_params).get("status")
        page = page_request(request, default_size=10, max_size=50)
        result = self.orders.page(
            self.actor,
            status=OrderStatus(status) if status else None,
            offset=page.offset,
            limit=page.page_size,
        )
        return page_response(
            request,
            page,
            total=result.total,
            results=OrderSummaryOutput(result.orders, many=True).data,
        )

    @extend_schema(responses=ClientOrderDetailOutput)
    def retrieve(self, request: Request, number: str) -> Response:
        return self.respond(ClientOrderDetailOutput, self.orders.detail(self.actor, number))

    @extend_schema(request=CancelInput, responses=ClientOrderDetailOutput)
    def cancel(self, request: Request, number: str) -> Response:
        command = self.parse(CancelInput, into=CancelOrder)
        return self.respond(
            ClientOrderDetailOutput, self.orders.cancel(self.actor, number, command)
        )


class DispatchViewSet(UseCaseViewSet):
    action_permissions = {
        "list": (ORDERS_VIEW_ASSIGNED,),
        "retrieve": (ORDERS_VIEW_ASSIGNED,),
        "assign": (ORDERS_ASSIGN,),
        "decline": (ORDERS_ASSIGNMENT_DECLINE,),
        "transition": (ORDERS_STATUS_ADVANCE,),
        "assignable": (ORDERS_ASSIGN,),
    }
    dispatch_orders = Inject(DispatchFacade)

    @extend_schema(parameters=[OrderFiltersInput], responses=page_of(OrderSummaryOutput))
    def list(self, request: Request) -> Response:
        filters = self.parse(OrderFiltersInput, into=OrderFilters, data=request.query_params)
        page = page_request(request, default_size=10, max_size=100)
        result = self.dispatch_orders.page(
            self.actor, filters, offset=page.offset, limit=page.page_size
        )
        return page_response(
            request,
            page,
            total=result.total,
            results=OrderSummaryOutput(result.orders, many=True).data,
            meta={"counts": result.counts},
        )

    @extend_schema(responses=OrderDetailOutput)
    def retrieve(self, request: Request, order_id: int) -> Response:
        return self.respond(OrderDetailOutput, self.dispatch_orders.detail(self.actor, order_id))

    @extend_schema(request=AssignInput, responses=OrderDetailOutput)
    def assign(self, request: Request, order_id: int) -> Response:
        command = self.parse(AssignInput, into=AssignOrder)
        return self.respond(
            OrderDetailOutput, self.dispatch_orders.assign(self.actor, order_id, command)
        )

    @extend_schema(request=DeclineInput, responses={204: None})
    def decline(self, request: Request, order_id: int) -> Response:
        self.dispatch_orders.decline(
            self.actor, order_id, self.parse(DeclineInput, into=DeclineAssignment)
        )
        return Response(status=204)

    @extend_schema(request=TransitionInput, responses=OrderDetailOutput)
    def transition(self, request: Request, order_id: int) -> Response:
        command = self.parse(TransitionInput, into=TransitionOrder)
        return self.respond(
            OrderDetailOutput, self.dispatch_orders.transition(self.actor, order_id, command)
        )

    @extend_schema(
        parameters=[OpenApiParameter("search", str, required=False)],
        responses=AssignableResellerOutput(many=True),
    )
    def assignable(self, request: Request) -> Response:
        search = request.query_params.get("search")
        resellers = self.dispatch_orders.assignable(str(search) if search else None)
        return self.respond(AssignableResellerOutput, resellers, many=True)
