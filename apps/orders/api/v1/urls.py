from django.urls import path

from apps.orders.api.v1.views import (
    CartMergeViewSet,
    CartViewSet,
    CheckoutViewSet,
    ClientOrderViewSet,
    DispatchViewSet,
    QuoteViewSet,
    TrackingViewSet,
)

urlpatterns = [
    path(
        "cart/",
        CartViewSet.as_view({"get": "retrieve", "delete": "destroy"}),
        name="cart",
    ),
    path("cart/items/", CartViewSet.as_view({"post": "create"}), name="cart-items"),
    path(
        "cart/items/<int:item_id>/",
        CartViewSet.as_view({"patch": "partial_update", "delete": "destroy_item"}),
        name="cart-item",
    ),
    path("cart/merge/", CartMergeViewSet.as_view({"post": "create"}), name="cart-merge"),
    path("checkout/quote/", QuoteViewSet.as_view({"post": "create"}), name="checkout-quote"),
    path("orders/", CheckoutViewSet.as_view({"post": "create"}), name="orders"),
    path("orders/track/", TrackingViewSet.as_view({"post": "create"}), name="order-tracking"),
    path("me/orders/", ClientOrderViewSet.as_view({"get": "list"}), name="my-orders"),
    path(
        "me/orders/<str:number>/",
        ClientOrderViewSet.as_view({"get": "retrieve"}),
        name="my-order",
    ),
    path(
        "me/orders/<str:number>/cancel/",
        ClientOrderViewSet.as_view({"post": "cancel"}),
        name="my-order-cancel",
    ),
    path("bo/orders/", DispatchViewSet.as_view({"get": "list"}), name="bo-orders"),
    path(
        "bo/orders/<int:order_id>/",
        DispatchViewSet.as_view({"get": "retrieve"}),
        name="bo-order",
    ),
    path(
        "bo/orders/<int:order_id>/assign/",
        DispatchViewSet.as_view({"post": "assign"}),
        name="bo-order-assign",
    ),
    path(
        "bo/orders/<int:order_id>/decline/",
        DispatchViewSet.as_view({"post": "decline"}),
        name="bo-order-decline",
    ),
    path(
        "bo/orders/<int:order_id>/transition/",
        DispatchViewSet.as_view({"post": "transition"}),
        name="bo-order-transition",
    ),
    path(
        "bo/resellers/assignable/",
        DispatchViewSet.as_view({"get": "assignable"}),
        name="bo-resellers-assignable",
    ),
]
