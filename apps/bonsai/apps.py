from django.apps import AppConfig


class BonsaiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.bonsai"
    label = "bonsai"
    verbose_name = "盆栽・品種"
