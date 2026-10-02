from decimal import Decimal

import pytest

from apps.orders.domain.pricing import (
    CouponKind,
    CouponTerms,
    QuoteLine,
    ShippingRules,
    discount_for,
    quote,
)
from apps.orders.services.shipping import normalize_city

LINES = [QuoteLine(unit_price=Decimal("60.00"), quantity=2, free_shipping=False, shipping_fee=None)]
KINSHASA = ShippingRules(free_threshold=Decimal("199.00"), flat_fee=Decimal("2.98"))
ELSEWHERE = ShippingRules(free_threshold=None, flat_fee=Decimal("7.50"), zone="Autres villes")


@pytest.mark.parametrize(
    ("terms", "subtotal", "expected"),
    [
        (CouponTerms(code="A", kind=CouponKind.PERCENT, value=Decimal(10)), "120.00", "12.00"),
        (CouponTerms(code="A", kind=CouponKind.PERCENT, value=Decimal("12.5")), "99.99", "12.50"),
        (
            CouponTerms(
                code="A", kind=CouponKind.PERCENT, value=Decimal(50), max_discount=Decimal(20)
            ),
            "120.00",
            "20",
        ),
        (CouponTerms(code="A", kind=CouponKind.FIXED, value=Decimal(15)), "120.00", "15"),
        (CouponTerms(code="A", kind=CouponKind.FIXED, value=Decimal(500)), "120.00", "120.00"),
    ],
)
def test_discounts(terms, subtotal, expected):
    assert discount_for(terms, Decimal(subtotal)) == Decimal(expected)


def test_quote_with_coupon_and_zone():
    coupon = CouponTerms(
        code="OFFERT", kind=CouponKind.FIXED, value=Decimal(20), free_shipping=True
    )

    plain = quote(LINES, ELSEWHERE)
    discounted = quote(LINES, ELSEWHERE, coupon)

    assert (plain.shipping_fee, plain.total, plain.free_shipping_remaining) == (
        Decimal("7.50"),
        Decimal("127.50"),
        None,
    )
    assert (discounted.discount, discounted.shipping_fee, discounted.total) == (
        Decimal(20),
        Decimal("0.00"),
        Decimal("100.00"),
    )
    assert quote(LINES, KINSHASA).free_shipping_remaining == Decimal("79.00")


def test_city_names_are_normalised():
    assert normalize_city("  KINSHASA ") == normalize_city("kinshasa")
    assert normalize_city("Mbuji-Mayi") == "mbuji mayi"
    assert normalize_city("Kisangani ") == normalize_city("KISANGANI")
    assert normalize_city("Bénin") == "benin"
