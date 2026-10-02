from apps.content.domain.read_models import CategoryBlock, HomePage
from apps.content.selectors import BannerSelector
from apps.content.services.contracts import Showcase
from core.domain.actor import Actor


class HomeService:
    def __init__(
        self,
        showcase: Showcase,
        banners: BannerSelector,
        *,
        section_size: int,
        category_blocks: int,
    ) -> None:
        self._showcase = showcase
        self._banners = banners
        self._section_size = section_size
        self._category_blocks = category_blocks

    def page(self, actor: Actor) -> HomePage:
        categories = [
            category for category in self._showcase.categories() if category.products_count
        ][: self._category_blocks]
        return HomePage(
            banners=self._banners.live(),
            deals=self._showcase.deals(actor, limit=self._section_size),
            new_arrivals=self._showcase.newest(actor, limit=self._section_size),
            best_sellers=self._showcase.best_sellers(actor, limit=self._section_size),
            categories=[
                CategoryBlock(
                    category=category,
                    products=self._showcase.in_category(
                        actor, category.slug, limit=self._section_size
                    ),
                )
                for category in categories
            ],
        )
