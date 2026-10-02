from core.domain.errors import Forbidden, NotFound, ServiceUnavailable, ValidationFailed


class UploadNotAllowed(Forbidden):
    default_code = "upload_not_allowed"
    default_detail = "Vous ne pouvez pas téléverser ce type de fichier."


class InvalidUpload(ValidationFailed):
    default_code = "invalid_upload"
    default_detail = "Le fichier téléversé n'a pas pu être vérifié."


class UploadTooLarge(ValidationFailed):
    default_code = "upload_too_large"
    default_detail = "Le fichier est trop volumineux."


class UnsupportedFormat(ValidationFailed):
    default_code = "unsupported_format"
    default_detail = "Format de fichier non pris en charge."


class MediaNotFound(NotFound):
    default_code = "media_not_found"
    default_detail = "Fichier introuvable."


class StorageNotConfigured(ServiceUnavailable):
    default_code = "storage_not_configured"
    default_detail = "Le stockage des fichiers n'est pas configuré."
