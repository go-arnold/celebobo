from django.urls import path

from apps.analytics.api.v1.views import AnalyticsViewSet, DashboardViewSet

DASHBOARD = {
    "summary/": "summary",
    "revenue-series/": "series",
    "payment-split/": "payment_split",
    "top-products/": "top_products",
    "recent-sales/": "recent_sales",
    "open-orders/": "open_orders",
}
ANALYTICS = {
    "categories/": "categories",
    "peak-hours/": "peak_hours",
    "sellers/": "sellers",
    "slow-movers/": "slow_movers",
}

urlpatterns = [
    *(
        path(
            f"bo/dashboard/{route}",
            DashboardViewSet.as_view({"get": action}),
            name=f"bo-dashboard-{action.replace('_', '-')}",
        )
        for route, action in DASHBOARD.items()
    ),
    *(
        path(
            f"bo/analytics/{route}",
            AnalyticsViewSet.as_view({"get": action}),
            name=f"bo-analytics-{action.replace('_', '-')}",
        )
        for route, action in ANALYTICS.items()
    ),
]
