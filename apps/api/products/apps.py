from django.apps import AppConfig


class ProductsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.products'

    def ready(self):
        from django.db.models.signals import post_save
        from django.dispatch import receiver
        from apps.products.models import ProductImage
        from apps.products.image_search import compute_phash

        @receiver(post_save, sender=ProductImage)
        def _compute_hash(sender, instance, **kwargs):
            if instance.image and not instance.image_hash:
                try:
                    instance.image.open()
                    h = compute_phash(instance.image)
                    instance.image.close()
                    ProductImage.objects.filter(pk=instance.pk).update(image_hash=h)
                except Exception:
                    pass
