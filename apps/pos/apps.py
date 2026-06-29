from django.apps import AppConfig


class PosConfig(AppConfig):
    name = 'apps.pos'
    label = 'pos'
    verbose_name = 'Point of Sale'
    default_auto_field = 'django.db.models.BigAutoField'

    def ready(self):
        pass  # no signals needed — POS uses billing signals via Invoice
