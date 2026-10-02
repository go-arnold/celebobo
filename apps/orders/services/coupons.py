from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

from apps.orders.domain.errors import CouponRejected
from apps.orders.domain.pricing import CouponTerms
from apps.orders.models import Coupon, Order
from apps.orders.repositories import CouponRepository


class CouponService:
    def __init__(self, coupons: CouponRepository, *, clock: Callable[[], datetime]) -> None:
        self._coupons = coupons
        self._clock = clock

    def terms(
        self, code: str, *, subtotal: Decimal, user_id: int | None, lock: bool = False
    ) -> tuple[Coupon, CouponTerms]:
        coupon = self._coupons.by_code(code, for_update=lock)
        if coupon is None:
            raise CouponRejected("unknown")
        self._check(coupon, subtotal=subtotal, user_id=user_id)
        return coupon, CouponTerms(
            code=coupon.code,
            kind=coupon.coupon_kind,
            value=coupon.value,
            max_discount=coupon.max_discount,
            free_shipping=coupon.free_shipping,
        )

    def redeem(self, coupon: Coupon, order: Order, *, user_id: int, amount: Decimal) -> None:
        self._coupons.redeem(coupon, order, user_id=user_id, amount=amount)

    def _check(self, coupon: Coupon, *, subtotal: Decimal, user_id: int | None) -> None:
        now = self._clock()
        if not coupon.is_active:
            raise CouponRejected("inactive")
        if coupon.starts_at and coupon.starts_at > now:
            raise CouponRejected("not_started")
        if coupon.ends_at and coupon.ends_at <= now:
            raise CouponRejected("expired")
        if subtotal < coupon.min_subtotal:
            raise CouponRejected("minimum", minimum=str(coupon.min_subtotal))
        if coupon.per_user_limit is not None and user_id is None:
            raise CouponRejected("login_required")
        total, mine = self._coupons.usage(coupon, user_id)
        if coupon.usage_limit is not None and total >= coupon.usage_limit:
            raise CouponRejected("exhausted")
        if coupon.per_user_limit is not None and mine >= coupon.per_user_limit:
            raise CouponRejected("already_used")
