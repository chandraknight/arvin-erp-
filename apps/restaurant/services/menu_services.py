from django.db import transaction
from ..models import Menu, MenuCategory, MenuItem


def get_published_menu(company):
    return (
        Menu.active_objects
        .filter(company=company, is_published=True)
        .prefetch_related(
            'categories__items__product',
        )
        .first()
    )


def get_active_categories(menu):
    if not menu:
        return []
    return menu.categories.filter(is_active=True).prefetch_related('items__product')


def publish_menu(menu: Menu, user) -> Menu:
    with transaction.atomic():
        # Unpublish all other menus for this company first
        Menu.objects.filter(company=menu.company, is_published=True).exclude(pk=menu.pk).update(is_published=False)
        menu.is_published = True
        menu.updated_by = user
        menu.save(update_fields=['is_published', 'updated_by'])
    return menu


def unpublish_menu(menu: Menu, user) -> Menu:
    menu.is_published = False
    menu.updated_by = user
    menu.save(update_fields=['is_published', 'updated_by'])
    return menu


def toggle_item_availability(item: MenuItem, user) -> MenuItem:
    item.is_available = not item.is_available
    item.updated_by = user
    item.save(update_fields=['is_available', 'updated_by'])
    return item
