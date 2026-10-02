SYSTEM_PROMPT = (
    "Tu es l'assistant de Celebobo, une boutique de téléphones et d'accessoires à Kinshasa.\n"
    "Réponds en français, de façon brève, chaleureuse et précise.\n"
    "Pour toute question sur des produits, des prix ou des disponibilités, appelle l'outil "
    "search_products et appuie-toi uniquement sur ses résultats ; n'invente jamais un produit, "
    "un prix ou un stock.\n"
    "Les prix sont en dollars américains. La livraison à Kinshasa prend 24 à 48 h.\n"
    "Si tu ne sais pas, dis-le et propose de contacter l'équipe."
)

MEMORY_PROMPT = "Résumé de la conversation jusqu'ici : {summary}"

SUMMARY_PROMPT = (
    "Mets à jour ce résumé de conversation entre un client et l'assistant de la boutique.\n"
    "Garde les besoins, le budget, les produits évoqués et les décisions. 80 mots maximum.\n\n"
    "Résumé actuel : {summary}\n\n"
    "Nouveaux échanges :\n{exchanges}"
)

INSIGHT_PROMPT = (
    "Analyse la question d'un client d'une boutique de téléphones.\n"
    'Réponds uniquement avec un objet JSON {{"sentiment": "positive|neutral|negative", '
    '"topic": "..."}} où topic est un ou deux mots en français '
    '(par exemple "prix", "livraison", "smartphone").\n\n'
    "Question : {question}"
)

SEARCH_TOOL_NAME = "search_products"
SEARCH_TOOL_DESCRIPTION = (
    "Recherche des produits du catalogue Celebobo par description en langage naturel, "
    "avec des filtres facultatifs."
)
SEARCH_TOOL_PARAMETERS = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Ce que cherche le client."},
        "category": {"type": "string", "description": "Slug de catégorie (ex. smartphones)."},
        "on_sale": {"type": "boolean", "description": "Uniquement les produits en promotion."},
        "max_price": {"type": "number", "description": "Prix maximum en dollars."},
    },
    "required": ["query"],
}
