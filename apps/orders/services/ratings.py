from django.db import IntegrityError, transaction

from apps.orders.domain.commands import RateReseller
from apps.orders.domain.enums import RATABLE_STATUSES
from apps.orders.domain.errors import AlreadyRated, OrderNotRatable
from apps.orders.models import Order, OrderRating


class RatingService:
    def rate(self, order: Order, command: RateReseller) -> OrderRating:
        if order.order_status not in RATABLE_STATUSES or order.assigned_reseller_id is None:
            raise OrderNotRatable
        try:
            with transaction.atomic():
                return OrderRating.objects.create(
                    order=order,
                    reseller_id=order.assigned_reseller_id,
                    client_id=order.client_id,
                    score=command.score,
                    comment=" ".join(command.comment.split())[:1000],
                )
        except IntegrityError as error:
            raise AlreadyRated from error
