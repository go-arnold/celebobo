from core.authz.catalog import permission_catalog
from core.domain.actor import Role

ORDERS_PLACE = "orders.place"
ORDERS_VIEW_MINE = "orders.view.mine"
ORDERS_CANCEL_MINE = "orders.cancel.mine"
ORDERS_VIEW_ASSIGNED = "orders.view.assigned"
ORDERS_STATUS_ADVANCE = "orders.status.advance"
ORDERS_ASSIGNMENT_DECLINE = "orders.assignment.decline"
ORDERS_VIEW_ALL = "orders.view.all"
ORDERS_ASSIGN = "orders.assign"
ORDERS_STATUS_ANY = "orders.status.any"

permission_catalog.grant(Role.CLIENT, ORDERS_PLACE, ORDERS_VIEW_MINE, ORDERS_CANCEL_MINE)
permission_catalog.grant(
    Role.RESELLER, ORDERS_VIEW_ASSIGNED, ORDERS_STATUS_ADVANCE, ORDERS_ASSIGNMENT_DECLINE
)
permission_catalog.grant(Role.MANAGER, ORDERS_VIEW_ALL, ORDERS_ASSIGN, ORDERS_STATUS_ANY)
