from apps.catalog.domain.read_models import CategoryView, ProductCard
from apps.content.domain.read_models import CategoryBlock, HomePage, SectionBlock
from apps.content.selectors import BannerSelector, SectionSelector
from apps.content.services.banners import by_placement, with_products
from apps.content.services.contracts import Showcase
from core.domain.actor import Actor


class HomeService:
    def __init__(
        self,
        showcase: Showcase,
        banners: BannerSelector,
        sections: SectionSelector,
        *,
        section_size: int,
        category_blocks: int,
    ) -> None:
        self._showcase = showcase
        self._banners = banners
        self._sections = sections
        self._section_size = section_size
        self._category_blocks = category_blocks

    def page(self, actor: Actor) -> HomePage:
        all_categories = self._showcase.categories()
        categories = [category for category in all_categories if category.products_count][
            : self._category_blocks
        ]
        return HomePage(
            banners=by_placement(with_products(self._banners.live(), self._showcase, actor)),
            deal=self._showcase.deal(actor),
            deals=self._showcase.deals(actor, limit=self._section_size),
            new_arrivals=self._showcase.newest(actor, limit=self._section_size),
            best_sellers=self._showcase.best_sellers(actor, limit=self._section_size),
            categories=[
                CategoryBlock(category=category, products=self._products(actor, category))
                for category in categories
            ],
            brands=self._showcase.brands(),
            sections=self._blocks(actor, all_categories),
        )

    def _blocks(self, actor: Actor, categories: list[CategoryView]) -> list[SectionBlock]:
        by_id = {category.id: category for category in flatten(categories)}
        return [
            SectionBlock(
                id=section.id,
                kind=section.kind,
                title=section.title or category.name,
                category=category,
                products=self._products(actor, category),
            )
            for section in self._sections.active()
            if (category := by_id.get(section.category_id)) is not None
        ]

    def _products(self, actor: Actor, category: CategoryView) -> list[ProductCard]:
        return self._showcase.in_category(actor, category.slug, limit=self._section_size)


def flatten(categories: list[CategoryView]) -> list[CategoryView]:
    return [nested for category in categories for nested in (category, *category.children)]
