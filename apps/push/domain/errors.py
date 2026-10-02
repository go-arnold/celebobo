from core.domain.errors import BusinessRuleViolation, NotFound


class DeviceNotFound(NotFound):
    default_code = "device_not_found"
    default_detail = "Appareil introuvable."


class TooManyDevices(BusinessRuleViolation):
    default_code = "too_many_devices"
    default_detail = "Trop d'appareils enregistrés pour ce compte."
