from core.authz.catalog import permission_catalog
from core.domain.actor import Role

CONTACT_INBOX = "contact.inbox"
NEWSLETTER_VIEW = "newsletter.view"
CONTENT_MANAGE = "content.manage"
SETTINGS_MANAGE = "settings.manage"

permission_catalog.grant(Role.MANAGER, CONTACT_INBOX, NEWSLETTER_VIEW, CONTENT_MANAGE)
permission_catalog.grant(Role.ADMIN, SETTINGS_MANAGE)
