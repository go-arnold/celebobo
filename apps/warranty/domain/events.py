from core.events.base import DomainEvent, domain_event


@domain_event
class ClaimSubmitted(DomainEvent):
    claim_id: int
    client_id: int
    order_id: int
    number: str = ""
    product: str = ""
    client_name: str = ""
    kind_label: str = ""


# every later step, for the client's notification and the audit log
@domain_event
class ClaimUpdated(DomainEvent):
    claim_id: int
    client_id: int
    status: str
    outcome: str | None = None
    number: str = ""
    # what the client is told (warranty policy steps)
    message: str = ""
