import csv
import io
from collections.abc import Callable
from typing import Any

from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from apps.content.api.v1.serializers import (
    AdminSettingsOutput,
    BannerFieldsInput,
    BannerOutput,
    ContactFiltersInput,
    ContactInput,
    ContactMessageOutput,
    FaqFieldsInput,
    FaqGroupOutput,
    FaqOutput,
    HandleContactInput,
    HomeOutput,
    PageFieldsInput,
    PageOutput,
    PageSummaryOutput,
    PublicSettingsOutput,
    SettingsInput,
    SubscribeInput,
    SubscriberFiltersInput,
    SubscriberOutput,
    SubscriptionOutput,
    UnsubscribeInput,
)
from apps.content.domain.commands import (
    BannerChanges,
    BannerFields,
    ContactFilters,
    FaqChanges,
    FaqFields,
    HandleContactMessage,
    PageChanges,
    PageFields,
    SendContactMessage,
    SettingsChanges,
)
from apps.content.facades import ContactFacade, NewsletterFacade, SiteContentFacade
from apps.content.permissions import (
    CONTACT_INBOX,
    CONTENT_MANAGE,
    NEWSLETTER_VIEW,
    SETTINGS_MANAGE,
)
from core.api.pagination import page_of, page_request, page_response
from core.api.views import UseCaseViewSet
from core.container import Inject


class PublicSiteViewSet(UseCaseViewSet):
    permission_classes = (AllowAny,)
    content = Inject(SiteContentFacade)

    @extend_schema(responses=HomeOutput)
    def home(self, request: Request) -> Response:
        return self.respond(HomeOutput, self.content.home(self.actor))

    @extend_schema(responses=PublicSettingsOutput)
    def site_settings(self, request: Request) -> Response:
        return self.respond(PublicSettingsOutput, self.content.public_settings())

    @extend_schema(responses=PageSummaryOutput(many=True))
    def pages(self, request: Request) -> Response:
        return self.respond(PageSummaryOutput, self.content.pages(published_only=True), many=True)

    @extend_schema(responses=PageOutput)
    def page(self, request: Request, slug: str) -> Response:
        return self.respond(PageOutput, self.content.page(slug))

    @extend_schema(responses=FaqGroupOutput(many=True))
    def faq(self, request: Request) -> Response:
        return self.respond(FaqGroupOutput, self.content.faq(), many=True)


class ContactViewSet(UseCaseViewSet):
    permission_classes = (AllowAny,)
    throttle_scope = "contact"
    contact = Inject(ContactFacade)

    @extend_schema(request=ContactInput, responses={202: None})
    def create(self, request: Request) -> Response:
        data = dict(self.validated(ContactInput))
        honeypot = data.pop("website")
        self.contact.send(self.actor, SendContactMessage(**data), spam=bool(honeypot))
        return Response(status=202)


class NewsletterViewSet(UseCaseViewSet):
    permission_classes = (AllowAny,)
    throttle_scope = "newsletter"
    newsletter = Inject(NewsletterFacade)

    @extend_schema(request=SubscribeInput, responses=SubscriptionOutput)
    def subscribe(self, request: Request) -> Response:
        data = self.validated(SubscribeInput)
        subscription = self.newsletter.subscribe(data["email"], source=data["source"])
        return self.respond(SubscriptionOutput, subscription)

    @extend_schema(request=UnsubscribeInput, responses={204: None})
    def unsubscribe(self, request: Request) -> Response:
        self.newsletter.unsubscribe(self.validated(UnsubscribeInput)["token"])
        return Response(status=204)


class ContactInboxViewSet(UseCaseViewSet):
    action_permissions = dict.fromkeys(("list", "retrieve", "partial_update"), (CONTACT_INBOX,))
    contact = Inject(ContactFacade)

    @extend_schema(parameters=[ContactFiltersInput], responses=page_of(ContactMessageOutput))
    def list(self, request: Request) -> Response:
        filters = self.parse(ContactFiltersInput, into=ContactFilters, data=request.query_params)
        page = page_request(request, default_size=20, max_size=100)
        messages, total, counts = self.contact.inbox(
            filters, offset=page.offset, limit=page.page_size
        )
        return page_response(
            request,
            page,
            total=total,
            results=ContactMessageOutput(messages, many=True).data,
            meta={"counts": counts},
        )

    @extend_schema(responses=ContactMessageOutput)
    def retrieve(self, request: Request, message_id: int) -> Response:
        return self.respond(ContactMessageOutput, self.contact.detail(message_id))

    @extend_schema(request=HandleContactInput, responses=ContactMessageOutput)
    def partial_update(self, request: Request, message_id: int) -> Response:
        command = self.parse(HandleContactInput, into=HandleContactMessage, partial=True)
        return self.respond(
            ContactMessageOutput, self.contact.handle(self.actor, message_id, command)
        )


class SubscriberViewSet(UseCaseViewSet):
    action_permissions = dict.fromkeys(("list", "export"), (NEWSLETTER_VIEW,))
    newsletter = Inject(NewsletterFacade)

    @extend_schema(parameters=[SubscriberFiltersInput], responses=page_of(SubscriberOutput))
    def list(self, request: Request) -> Response:
        filters = self.validated(SubscriberFiltersInput, data=request.query_params)
        page = page_request(request, default_size=50, max_size=200)
        subscribers, total = self.newsletter.subscribers(
            active=filters["active"],
            search=filters.get("search"),
            offset=page.offset,
            limit=page.page_size,
        )
        return page_response(
            request, page, total=total, results=SubscriberOutput(subscribers, many=True).data
        )

    @extend_schema(
        parameters=[SubscriberFiltersInput], responses={(200, "text/csv"): OpenApiTypes.STR}
    )
    def export(self, request: Request) -> HttpResponse:
        active = self.validated(SubscriberFiltersInput, data=request.query_params)["active"]
        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=";")
        writer.writerow(["email", "source", "actif", "inscrit le", "désinscrit le"])
        for subscriber in self.newsletter.export(active=active):
            writer.writerow(
                [
                    subscriber.email,
                    subscriber.source,
                    "1" if subscriber.is_active else "0",
                    subscriber.subscribed_at.isoformat(),
                    subscriber.unsubscribed_at.isoformat() if subscriber.unsubscribed_at else "",
                ]
            )
        response = HttpResponse("﻿" + buffer.getvalue(), content_type="text/csv; charset=utf-8")
        stamp = timezone.localtime().strftime("%Y%m%d")
        response["Content-Disposition"] = f'attachment; filename="abonnes-{stamp}.csv"'
        return response


class SettingsViewSet(UseCaseViewSet):
    action_permissions = dict.fromkeys(("retrieve", "partial_update"), (SETTINGS_MANAGE,))
    content = Inject(SiteContentFacade)

    @extend_schema(responses=AdminSettingsOutput)
    def retrieve(self, request: Request) -> Response:
        return self.respond(AdminSettingsOutput, self.content.admin_settings())

    @extend_schema(request=SettingsInput, responses=AdminSettingsOutput)
    def partial_update(self, request: Request) -> Response:
        changes = self.parse(SettingsInput, into=SettingsChanges, partial=True)
        return self.respond(AdminSettingsOutput, self.content.update_settings(self.actor, changes))


def editor_viewset(
    *,
    name: str,
    fields_input: type[Any],
    output: type[Any],
    fields: type[Any],
    changes: type[Any],
    listing: Callable[[SiteContentFacade], list[Any]],
    section: str,
) -> type[UseCaseViewSet]:
    def list_(self: Any, request: Request) -> Response:
        response: Response = self.respond(output, listing(self.content), many=True)
        return response

    def create(self: Any, request: Request) -> Response:
        command = self.parse(fields_input, into=fields)
        created = getattr(self.content, f"create_{section}")(self.actor, command)
        response: Response = self.respond(output, created, status=201)
        return response

    def partial_update(self: Any, request: Request, item_id: int) -> Response:
        command = self.parse(fields_input, into=changes, partial=True)
        updated = getattr(self.content, f"update_{section}")(self.actor, item_id, command)
        response: Response = self.respond(output, updated)
        return response

    def destroy(self: Any, request: Request, item_id: int) -> Response:
        getattr(self.content, f"delete_{section}")(self.actor, item_id)
        return Response(status=204)

    attributes = {
        "action_permissions": dict.fromkeys(
            ("list", "create", "partial_update", "destroy"), (CONTENT_MANAGE,)
        ),
        "content": Inject(SiteContentFacade),
        "list": extend_schema(responses=output(many=True))(list_),
        "create": extend_schema(request=fields_input, responses={201: output})(create),
        "partial_update": extend_schema(request=fields_input, responses=output)(partial_update),
        "destroy": extend_schema(responses={204: None})(destroy),
    }
    return type(name, (UseCaseViewSet,), attributes)


PageAdminViewSet = editor_viewset(
    name="PageAdminViewSet",
    fields_input=PageFieldsInput,
    output=PageOutput,
    fields=PageFields,
    changes=PageChanges,
    listing=lambda content: content.pages(published_only=False),
    section="page",
)
FaqAdminViewSet = editor_viewset(
    name="FaqAdminViewSet",
    fields_input=FaqFieldsInput,
    output=FaqOutput,
    fields=FaqFields,
    changes=FaqChanges,
    listing=lambda content: content.faq_entries(),
    section="faq",
)
BannerAdminViewSet = editor_viewset(
    name="BannerAdminViewSet",
    fields_input=BannerFieldsInput,
    output=BannerOutput,
    fields=BannerFields,
    changes=BannerChanges,
    listing=lambda content: content.banners(),
    section="banner",
)
