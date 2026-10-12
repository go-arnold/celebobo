HOME = "home"
SITEMAP = "sitemap"
# sections of the site settings that show on the home page; pages only appear in the sitemap
HOME_SECTIONS = frozenset({"settings", "banners", "faq", "brands", "sections"})


def product_tags(slug: str, category_slug: str) -> tuple[str, ...]:
    return (f"product:{slug}", f"category:{category_slug}", HOME, SITEMAP)


def category_tags(slug: str) -> tuple[str, ...]:
    return (f"category:{slug}", HOME, SITEMAP)


def section_tags(section: str) -> tuple[str, ...]:
    return (HOME,) if section in HOME_SECTIONS else (SITEMAP,)
