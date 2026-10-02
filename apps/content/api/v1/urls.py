from typing import Any

from django.urls import path

from apps.content.api.v1.views import (
    BannerAdminViewSet,
    ContactInboxViewSet,
    ContactViewSet,
    FaqAdminViewSet,
    NewsletterViewSet,
    PageAdminViewSet,
    PublicSiteViewSet,
    SettingsViewSet,
    SubscriberViewSet,
)

COLLECTION: dict[str, Any] = {"get": "list", "post": "create"}
ITEM: dict[str, Any] = {"patch": "partial_update", "delete": "destroy"}

urlpatterns = [
    path("home/", PublicSiteViewSet.as_view({"get": "home"}), name="home"),
    path(
        "settings/public/",
        PublicSiteViewSet.as_view({"get": "site_settings"}),
        name="settings-public",
    ),
    path("pages/", PublicSiteViewSet.as_view({"get": "pages"}), name="pages"),
    path("pages/<slug:slug>/", PublicSiteViewSet.as_view({"get": "page"}), name="page"),
    path("faq/", PublicSiteViewSet.as_view({"get": "faq"}), name="faq"),
    path("contact/", ContactViewSet.as_view({"post": "create"}), name="contact"),
    path(
        "newsletter/subscribe/",
        NewsletterViewSet.as_view({"post": "subscribe"}),
        name="newsletter-subscribe",
    ),
    path(
        "newsletter/unsubscribe/",
        NewsletterViewSet.as_view({"post": "unsubscribe"}),
        name="newsletter-unsubscribe",
    ),
    path(
        "bo/settings/",
        SettingsViewSet.as_view({"get": "retrieve", "patch": "partial_update"}),
        name="bo-settings",
    ),
    path(
        "bo/contact-messages/",
        ContactInboxViewSet.as_view({"get": "list"}),
        name="bo-contact-messages",
    ),
    path(
        "bo/contact-messages/<id:message_id>/",
        ContactInboxViewSet.as_view({"get": "retrieve", "patch": "partial_update"}),
        name="bo-contact-message",
    ),
    path(
        "bo/newsletter/subscribers/",
        SubscriberViewSet.as_view({"get": "list"}),
        name="bo-newsletter-subscribers",
    ),
    path(
        "bo/newsletter/subscribers/export/",
        SubscriberViewSet.as_view({"get": "export"}),
        name="bo-newsletter-export",
    ),
    path("bo/pages/", PageAdminViewSet.as_view(COLLECTION), name="bo-pages"),
    path("bo/pages/<id:item_id>/", PageAdminViewSet.as_view(ITEM), name="bo-page"),
    path("bo/faq/", FaqAdminViewSet.as_view(COLLECTION), name="bo-faq"),
    path("bo/faq/<id:item_id>/", FaqAdminViewSet.as_view(ITEM), name="bo-faq-entry"),
    path("bo/banners/", BannerAdminViewSet.as_view(COLLECTION), name="bo-banners"),
    path("bo/banners/<id:item_id>/", BannerAdminViewSet.as_view(ITEM), name="bo-banner"),
]
