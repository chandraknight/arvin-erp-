from django.urls import path
from . import views

app_name = 'pos'

urlpatterns = [
    # Main terminal
    path('', views.pos_terminal, name='terminal'),

    # Cart HTMX endpoints
    path('cart/add/',       views.pos_add_item,    name='add_item'),
    path('cart/update/',    views.pos_update_qty,  name='update_qty'),
    path('cart/remove/',    views.pos_remove_item, name='remove_item'),
    path('cart/customer/',  views.pos_set_customer, name='set_customer'),
    path('cart/referrer/',  views.pos_set_referrer, name='set_referrer'),
    path('cart/referrer/new/', views.pos_create_referrer, name='create_referrer'),
    path('cart/discount/',  views.pos_set_discount,        name='set_discount'),
    path('cart/delivery/',  views.pos_set_delivery_charge, name='set_delivery_charge'),
    path('cart/clear/',     views.pos_clear_cart,          name='clear_cart'),

    # Checkout
    path('checkout/',                  views.pos_checkout, name='checkout'),
    path('receipt/<uuid:pk>/',         views.pos_receipt,  name='receipt'),

    # Sales history
    path('sales/',                     views.pos_sale_list, name='sale_list'),

    # Product / referrer search JSON
    path('api/products/',              views.pos_product_search,  name='product_search'),
    path('api/referrers/',             views.pos_referrer_search, name='referrer_search'),
]
