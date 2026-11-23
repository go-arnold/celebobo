from decimal import Decimal

from core.events.base import DomainEvent, domain_event


# created, changed, ended early or deleted (audit)
@domain_event
class CampaignChanged(DomainEvent):
    campaign_id: int
    change: str
    actor_id: int | None = None


# a Mobile Money cashback sent by staff: the client is told
@domain_event
class CashbackPaid(DomainEvent):
    reward_id: int
    client_id: int
    order_number: str
    amount: Decimal
    reference: str = ""
    actor_id: int | None = None
