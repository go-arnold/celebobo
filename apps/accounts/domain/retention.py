# privacy policy, section 6: a client account is kept while it is active, then 3 years after the
# client's last activity, and anonymised. The last activity is the latest of: sign-up, last login,
# last session renewal (refresh token), last order placed (whatever became of it), last message
# sent, last points movement following an order or a return (expiry and resellers' referral
# points are not the client's doing).
#
# Only plain client accounts are concerned: staff, resellers and former resellers (they keep a
# referral code) are left alone, since the reseller partnership and its commissions are kept
# 10 years for the accounts.
INACTIVITY_YEARS = 3

ANONYMIZED_EMAIL_DOMAIN = "deleted.invalid"


# unique per account, like the address it replaces; `.invalid` can never receive mail
def anonymized_email(user_id: int) -> str:
    return f"deleted-{user_id}@{ANONYMIZED_EMAIL_DOMAIN}"
