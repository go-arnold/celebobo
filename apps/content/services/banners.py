from collections import defaultdict
from dataclasses import replace

from apps.content.domain.read_models import BannerView
from apps.content.services.contracts import Showcase
from core.domain.actor import Actor


def with_products(banners: list[BannerView], showcase: Showcase, actor: Actor) -> list[BannerView]:
    ids = list(dict.fromkeys(banner.product_id for banner in banners if banner.product_id))
    cards = {card.id: card for card in showcase.cards(actor, ids)} if ids else {}
    return [
        replace(banner, product=cards.get(banner.product_id)) if banner.product_id else banner
        for banner in banners
    ]


def by_placement(banners: list[BannerView]) -> dict[str, list[BannerView]]:
    grouped: defaultdict[str, list[BannerView]] = defaultdict(list)
    for banner in banners:
        grouped[banner.placement].append(banner)
    return dict(grouped)
