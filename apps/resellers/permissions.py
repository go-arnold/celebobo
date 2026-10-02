from core.authz.catalog import permission_catalog
from core.domain.actor import Role

REFERRAL_VIEW_OWN = "referral.view.own"
RESELLERS_VIEW = "resellers.view"
RESELLERS_MANAGE = "resellers.manage"
APPLICATIONS_REVIEW = "reseller_applications.review"

permission_catalog.grant(Role.RESELLER, REFERRAL_VIEW_OWN)
permission_catalog.grant(Role.MANAGER, RESELLERS_VIEW, RESELLERS_MANAGE, APPLICATIONS_REVIEW)
