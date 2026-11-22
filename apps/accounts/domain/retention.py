from enum import Enum

# privacy policy, section 6: a client account is kept while it is active, then 3 years after the
# client's last activity, and anonymised. The last activity is the latest of: sign-up, last login,
# last session renewal (refresh token), last order placed (whatever became of it), last message
# sent, last points movement following an order or a return (expiry and resellers' referral
# points are not the client's doing).
#
# Only plain client accounts are concerned: staff, resellers and former resellers (they keep a
# referral code) are left alone, since the reseller partnership and its commissions are kept
# 10 years for the accounts.
#
# A client who deleted their account (`DELETE /me/`) lost their identity at once, but their orders
# kept a phone, notes and delivery codes, their ratings a comment, and so on. Those go 3 years
# after the deletion (the last activity of the account), former resellers included: their
# commissions are in the sales ledger, which is not touched. `personal_data_erased_at` marks the
# accounts done, so none is processed twice.
INACTIVITY_YEARS = 3


class Outcome(Enum):
    # the account was not due any more (the client came back, or another run got it first)
    SKIPPED = "skipped"
    # identity scrubbed and personal data erased (inactive account)
    ANONYMIZED = "anonymized"
    # personal data erased 3 years after the client deleted the account
    ERASED = "erased"


# privacy policy, section 6: the consent to commercial offers lasts until it is withdrawn, or
# 3 years without interaction with us. An interaction is giving the consent (again) or any
# activity counted for the account above (login, session renewal, order, message, points movement).
MARKETING_CONSENT_YEARS = 3

ANONYMIZED_EMAIL_DOMAIN = "deleted.invalid"


# unique per account, like the address it replaces; `.invalid` can never receive mail
def anonymized_email(user_id: int) -> str:
    return f"deleted-{user_id}@{ANONYMIZED_EMAIL_DOMAIN}"
