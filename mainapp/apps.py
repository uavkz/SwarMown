from django.apps import AppConfig


class MainappConfig(AppConfig):
    name = "mainapp"

    def ready(self):
        from mainapp.patches import apply_patches

        apply_patches()
