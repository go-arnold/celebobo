from core.domain.errors import Conflict


class PointsUnavailable(Conflict):
    default_code = "points_unavailable"
    default_detail = "Votre solde de points a changé. Vérifiez le montant puis confirmez."
