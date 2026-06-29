from django.urls import path
from apps.ecom.views import storefront, admin as ecom_admin, cms_admin, media

app_name = 'ecom'

urlpatterns = [
    # ── Public storefront ──────────────────────────────────
    path('', storefront.store_home, name='home'),
    path('shop/', storefront.product_list, name='product_list'),
    path('shop/image-search/', storefront.image_search, name='image_search'),
    path('product/<uuid:product_id>/', storefront.product_detail, name='product_detail'),
    path('cart/', storefront.cart_view, name='cart'),
    path('cart/add/<uuid:product_id>/', storefront.add_to_cart, name='add_to_cart'),
    path('cart/remove/<uuid:product_id>/', storefront.remove_from_cart, name='remove_from_cart'),
    path('cart/update/<uuid:product_id>/', storefront.update_cart, name='update_cart'),
    path('checkout/', storefront.checkout, name='checkout'),
    path('checkout/place/', storefront.place_order, name='place_order'),
    path('order/success/<str:order_number>/', storefront.order_success, name='order_success'),
    path('track/', storefront.track_order, name='track_order'),
    path('p/<slug:slug>/', storefront.static_page, name='static_page'),

    # ── Blog ──────────────────────────────────────────────
    path('blog/', storefront.blog_list, name='blog_list'),
    path('blog/<slug:slug>/', storefront.blog_detail, name='blog_detail'),

    # ── Bundles / Packages ────────────────────────────────
    path('bundles/', storefront.bundle_list, name='bundle_list'),
    path('bundles/<uuid:bundle_id>/', storefront.bundle_detail, name='bundle_detail'),
    path('bundles/<uuid:bundle_id>/add-to-cart/', storefront.add_bundle_to_cart, name='add_bundle_to_cart'),

    # ── Contact ───────────────────────────────────────────
    path('contact/', storefront.contact_us, name='contact'),

    # ── Customer auth ─────────────────────────────────────
    path('login/', storefront.customer_login, name='login'),
    path('register/', storefront.customer_register, name='register'),
    path('logout/', storefront.customer_logout, name='customer_logout'),
    path('account/', storefront.customer_account, name='account'),

    # ── ERP admin control ─────────────────────────────────
    path('manage/', ecom_admin.dashboard, name='admin_dashboard'),
    path('manage/products/', ecom_admin.product_list, name='admin_product_list'),
    path('manage/products/<uuid:product_id>/toggle/', ecom_admin.toggle_product_ecom, name='admin_toggle_product'),
    path('manage/products/bulk-toggle/', ecom_admin.bulk_toggle_ecom, name='admin_bulk_toggle'),
    path('manage/orders/', ecom_admin.order_list, name='admin_order_list'),
    path('manage/orders/<uuid:order_id>/', ecom_admin.order_detail, name='admin_order_detail'),
    path('manage/orders/<uuid:order_id>/status/', ecom_admin.update_order_status, name='admin_update_order_status'),
    path('manage/orders/<uuid:order_id>/cod/', ecom_admin.update_cod_status, name='admin_update_cod_status'),
    path('manage/orders/<uuid:order_id>/slip/', ecom_admin.order_print_slip, name='admin_order_print_slip'),
    path('manage/orders/<uuid:order_id>/create-so/', ecom_admin.order_create_sales_order, name='admin_order_create_so'),
    path('manage/inventory/', ecom_admin.ecom_inventory, name='admin_ecom_inventory'),
    path('manage/categories/images/', ecom_admin.category_image_list, name='admin_category_images'),
    path('manage/categories/<uuid:category_id>/image/', ecom_admin.update_category_image, name='admin_update_category_image'),

    # ── Packages admin ────────────────────────────────────
    path('manage/packages/', ecom_admin.package_list, name='admin_package_list'),
    path('manage/packages/create/', ecom_admin.package_create, name='admin_package_create'),
    path('manage/packages/<uuid:package_id>/edit/', ecom_admin.package_edit, name='admin_package_edit'),
    path('manage/packages/<uuid:package_id>/delete/', ecom_admin.package_delete, name='admin_package_delete'),

    # ── Coupons ───────────────────────────────────────────
    path('manage/coupons/', ecom_admin.coupon_list, name='coupon_list'),
    path('manage/coupons/create/', ecom_admin.coupon_create, name='coupon_create'),
    path('manage/coupons/<uuid:coupon_id>/toggle/', ecom_admin.coupon_toggle, name='coupon_toggle'),
    path('coupon/validate/', storefront.validate_coupon_view, name='validate_coupon'),

    # ── Media Manager ─────────────────────────────────────
    path('manage/media/', media.media_library, name='media_library'),
    path('manage/media/optimize/', media.media_optimize, name='media_optimize'),
    path('manage/media/replace/', media.media_replace, name='media_replace'),
    path('manage/media/delete/', media.media_delete, name='media_delete'),
    path('manage/media/upload/', media.media_upload, name='media_upload'),
    path('manage/media/folder/create/', media.media_folder_create, name='media_folder_create'),
    path('manage/media/folder/delete/', media.media_folder_delete, name='media_folder_delete'),

    # ── CMS ───────────────────────────────────────────────
    path('manage/cms/', cms_admin.cms_dashboard, name='cms_dashboard'),
    path('manage/cms/settings/', cms_admin.site_settings, name='cms_settings'),
    path('manage/cms/banners/', cms_admin.banner_list, name='cms_banner_list'),
    path('manage/cms/banners/add/', cms_admin.banner_create, name='cms_banner_create'),
    path('manage/cms/banners/<uuid:banner_id>/edit/', cms_admin.banner_edit, name='cms_banner_edit'),
    path('manage/cms/banners/<uuid:banner_id>/delete/', cms_admin.banner_delete, name='cms_banner_delete'),
    path('manage/cms/banners/<uuid:banner_id>/toggle/', cms_admin.banner_toggle, name='cms_banner_toggle'),
    path('manage/cms/pages/', cms_admin.page_list, name='cms_page_list'),
    path('manage/cms/pages/add/', cms_admin.page_create, name='cms_page_create'),
    path('manage/cms/pages/<uuid:page_id>/edit/', cms_admin.page_edit, name='cms_page_edit'),
    path('manage/cms/pages/<uuid:page_id>/delete/', cms_admin.page_delete, name='cms_page_delete'),
    path('manage/cms/announcements/', cms_admin.announcement_list, name='cms_announcement_list'),
    path('manage/cms/announcements/add/', cms_admin.announcement_create, name='cms_announcement_create'),
    path('manage/cms/announcements/<uuid:ann_id>/edit/', cms_admin.announcement_edit, name='cms_announcement_edit'),
    path('manage/cms/announcements/<uuid:ann_id>/delete/', cms_admin.announcement_delete, name='cms_announcement_delete'),
    path('manage/cms/announcements/<uuid:ann_id>/toggle/', cms_admin.announcement_toggle, name='cms_announcement_toggle'),

    # ── CMS: Blog ─────────────────────────────────────────
    path('manage/cms/blog/', cms_admin.blog_list, name='cms_blog_list'),
    path('manage/cms/blog/add/', cms_admin.blog_create, name='cms_blog_create'),
    path('manage/cms/blog/<uuid:post_id>/edit/', cms_admin.blog_edit, name='cms_blog_edit'),
    path('manage/cms/blog/<uuid:post_id>/delete/', cms_admin.blog_delete, name='cms_blog_delete'),

    # ── CMS: Contacts ─────────────────────────────────────
    path('manage/cms/contacts/', cms_admin.contact_list, name='cms_contact_list'),
    path('manage/cms/contacts/<uuid:msg_id>/', cms_admin.contact_detail, name='cms_contact_detail'),
    path('manage/cms/contacts/<uuid:msg_id>/read/', cms_admin.contact_mark_read, name='cms_contact_mark_read'),

    # ── CMS: Product E-Commerce Content ───────────────────
    path('manage/cms/products/', cms_admin.product_content_list, name='cms_product_content_list'),
    path('manage/cms/products/<uuid:product_id>/content/', cms_admin.product_content_edit, name='cms_product_content_edit'),
    path('manage/cms/images/<uuid:image_id>/delete/', cms_admin.product_image_delete, name='cms_product_image_delete'),
]
