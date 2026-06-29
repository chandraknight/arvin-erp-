"""
ERP admin views for the ecom CMS.
Manages site settings, hero banners, static pages, and announcements.
All views require staff login.
"""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils.text import slugify

from django.utils import timezone
from apps.ecom.models import SiteSettings, HeroBanner, Page, Announcement, BlogPost, ContactMessage
from apps.company.models import Company
from apps.products.models import Product, ProductImage
from apps.products.forms import ProductImageFormSet


def _get_company(request):
    return request.user.profile.company if hasattr(request.user, 'profile') else Company.objects.first()


def _get_or_create_settings(company):
    obj, _ = SiteSettings.objects.get_or_create(company=company)
    return obj


# ── Site Settings ─────────────────────────────────────────────────────────────

@login_required
def cms_dashboard(request):
    company = _get_company(request)
    settings = _get_or_create_settings(company)
    banners = HeroBanner.objects.filter(company=company)
    pages = Page.objects.filter(company=company)
    announcements = Announcement.objects.filter(company=company)
    blog_count = BlogPost.objects.filter(company=company).count()
    return render(request, 'ecom/admin/cms/dashboard.html', {
        'settings': settings,
        'banners': banners,
        'pages': pages,
        'announcements': announcements,
        'blog_count': blog_count,
    })


@login_required
def site_settings(request):
    company = _get_company(request)
    settings = _get_or_create_settings(company)

    if request.method == 'POST':
        settings.store_name = request.POST.get('store_name', '').strip()
        settings.tagline = request.POST.get('tagline', '').strip()
        settings.contact_phone = request.POST.get('contact_phone', '').strip()
        settings.contact_email = request.POST.get('contact_email', '').strip()
        settings.contact_address = request.POST.get('contact_address', '').strip()
        settings.facebook_url = request.POST.get('facebook_url', '').strip()
        settings.instagram_url = request.POST.get('instagram_url', '').strip()
        settings.tiktok_url = request.POST.get('tiktok_url', '').strip()
        settings.twitter_url = request.POST.get('twitter_url', '').strip()
        settings.footer_text = request.POST.get('footer_text', '').strip()
        settings.free_shipping_threshold = int(request.POST.get('free_shipping_threshold', 5000) or 5000)
        from decimal import Decimal
        try:
            settings.delivery_charge = Decimal(request.POST.get('delivery_charge', '0') or '0')
        except Exception:
            settings.delivery_charge = Decimal('0.00')
        settings.show_topbar = 'show_topbar' in request.POST
        settings.show_special_offer = 'show_special_offer' in request.POST
        if request.FILES.get('logo'):
            settings.logo = request.FILES['logo']
        if request.FILES.get('favicon'):
            settings.favicon = request.FILES['favicon']
        settings.save()
        messages.success(request, 'Site settings saved.')
        return redirect('ecom:cms_settings')

    return render(request, 'ecom/admin/cms/site_settings.html', {'settings': settings})


# ── Hero Banners ──────────────────────────────────────────────────────────────

@login_required
def banner_list(request):
    company = _get_company(request)
    banners = HeroBanner.objects.filter(company=company)
    return render(request, 'ecom/admin/cms/banner_list.html', {'banners': banners})


@login_required
def banner_create(request):
    company = _get_company(request)
    if request.method == 'POST':
        if not request.FILES.get('image'):
            messages.error(request, 'An image is required.')
            return redirect('ecom:cms_banner_list')
        HeroBanner.objects.create(
            company=company,
            banner_type=request.POST.get('banner_type', 'HERO'),
            title=request.POST.get('title', '').strip(),
            subtitle=request.POST.get('subtitle', '').strip(),
            image=request.FILES['image'],
            link_url=request.POST.get('link_url', '').strip(),
            link_label=request.POST.get('link_label', '').strip(),
            sort_order=int(request.POST.get('sort_order', 0)),
            is_active=bool(request.POST.get('is_active')),
        )
        messages.success(request, 'Banner added.')
        return redirect('ecom:cms_banner_list')
    return render(request, 'ecom/admin/cms/banner_form.html', {'banner': None})


@login_required
def banner_edit(request, banner_id):
    company = _get_company(request)
    banner = get_object_or_404(HeroBanner, id=banner_id, company=company)
    if request.method == 'POST':
        banner.banner_type = request.POST.get('banner_type', 'HERO')
        banner.title = request.POST.get('title', '').strip()
        banner.subtitle = request.POST.get('subtitle', '').strip()
        banner.link_url = request.POST.get('link_url', '').strip()
        banner.link_label = request.POST.get('link_label', '').strip()
        banner.sort_order = int(request.POST.get('sort_order', 0))
        banner.is_active = bool(request.POST.get('is_active'))
        if request.FILES.get('image'):
            banner.image = request.FILES['image']
        banner.save()
        messages.success(request, 'Banner updated.')
        return redirect('ecom:cms_banner_list')
    return render(request, 'ecom/admin/cms/banner_form.html', {'banner': banner})


@login_required
@require_POST
def banner_delete(request, banner_id):
    company = _get_company(request)
    banner = get_object_or_404(HeroBanner, id=banner_id, company=company)
    banner.delete()
    messages.success(request, 'Banner deleted.')
    return redirect('ecom:cms_banner_list')


@login_required
@require_POST
def banner_toggle(request, banner_id):
    company = _get_company(request)
    banner = get_object_or_404(HeroBanner, id=banner_id, company=company)
    banner.is_active = not banner.is_active
    banner.save(update_fields=['is_active'])
    return redirect('ecom:cms_banner_list')


# ── Pages ─────────────────────────────────────────────────────────────────────

@login_required
def page_list(request):
    company = _get_company(request)
    pages = Page.objects.filter(company=company)
    return render(request, 'ecom/admin/cms/page_list.html', {'pages': pages})


@login_required
def page_create(request):
    company = _get_company(request)
    from apps.ecom.models import PAGE_SLUG_CHOICES
    if request.method == 'POST':
        slug_type = request.POST.get('slug_type', 'custom')
        title = request.POST.get('title', '').strip()
        slug = request.POST.get('slug', '').strip() or slugify(title)
        if Page.objects.filter(company=company, slug=slug).exists():
            messages.error(request, f'A page with slug "{slug}" already exists.')
            return redirect('ecom:cms_page_create')
        Page.objects.create(
            company=company,
            slug_type=slug_type,
            slug=slug,
            title=title,
            content=request.POST.get('content', ''),
            is_published=bool(request.POST.get('is_published')),
            show_in_footer=bool(request.POST.get('show_in_footer')),
            show_in_nav=bool(request.POST.get('show_in_nav')),
        )
        messages.success(request, f'Page "{title}" created.')
        return redirect('ecom:cms_page_list')
    return render(request, 'ecom/admin/cms/page_form.html', {
        'page': None,
        'slug_choices': PAGE_SLUG_CHOICES,
    })


@login_required
def page_edit(request, page_id):
    company = _get_company(request)
    from apps.ecom.models import PAGE_SLUG_CHOICES
    page = get_object_or_404(Page, id=page_id, company=company)
    if request.method == 'POST':
        page.slug_type = request.POST.get('slug_type', page.slug_type)
        page.title = request.POST.get('title', '').strip()
        page.content = request.POST.get('content', '')
        page.is_published = bool(request.POST.get('is_published'))
        page.show_in_footer = bool(request.POST.get('show_in_footer'))
        page.show_in_nav = bool(request.POST.get('show_in_nav'))
        page.save()
        messages.success(request, 'Page updated.')
        return redirect('ecom:cms_page_list')
    return render(request, 'ecom/admin/cms/page_form.html', {
        'page': page,
        'slug_choices': PAGE_SLUG_CHOICES,
    })


@login_required
@require_POST
def page_delete(request, page_id):
    company = _get_company(request)
    page = get_object_or_404(Page, id=page_id, company=company)
    page.delete()
    messages.success(request, 'Page deleted.')
    return redirect('ecom:cms_page_list')


# ── Announcements ─────────────────────────────────────────────────────────────

@login_required
def announcement_list(request):
    company = _get_company(request)
    announcements = Announcement.objects.filter(company=company)
    return render(request, 'ecom/admin/cms/announcement_list.html', {'announcements': announcements})


@login_required
def announcement_create(request):
    company = _get_company(request)
    from apps.ecom.models import Announcement
    if request.method == 'POST':
        import datetime
        expires_raw = request.POST.get('expires_at', '').strip()
        expires_at = None
        if expires_raw:
            from django.utils.dateparse import parse_datetime, parse_date
            from datetime import datetime, time
            expires_at = parse_datetime(expires_raw) or (
                datetime.combine(parse_date(expires_raw), time(23, 59)) if parse_date(expires_raw) else None
            )
        Announcement.objects.create(
            company=company,
            announcement_type=request.POST.get('announcement_type', 'BANNER'),
            text=request.POST.get('text', '').strip(),
            link_url=request.POST.get('link_url', '').strip(),
            link_label=request.POST.get('link_label', '').strip(),
            bg_color=request.POST.get('bg_color', 'indigo').strip(),
            is_active=bool(request.POST.get('is_active')),
            expires_at=expires_at,
            sort_order=int(request.POST.get('sort_order', 0)),
        )
        messages.success(request, 'Announcement created.')
        return redirect('ecom:cms_announcement_list')
    return render(request, 'ecom/admin/cms/announcement_form.html', {'announcement': None})


@login_required
def announcement_edit(request, ann_id):
    company = _get_company(request)
    ann = get_object_or_404(Announcement, id=ann_id, company=company)
    if request.method == 'POST':
        from django.utils.dateparse import parse_datetime
        expires_raw = request.POST.get('expires_at', '').strip()
        ann.announcement_type = request.POST.get('announcement_type', ann.announcement_type)
        ann.text = request.POST.get('text', '').strip()
        ann.link_url = request.POST.get('link_url', '').strip()
        ann.link_label = request.POST.get('link_label', '').strip()
        ann.bg_color = request.POST.get('bg_color', 'indigo').strip()
        ann.is_active = bool(request.POST.get('is_active'))
        if expires_raw:
            from django.utils.dateparse import parse_datetime, parse_date
            from datetime import datetime, time
            ann.expires_at = parse_datetime(expires_raw) or (
                datetime.combine(parse_date(expires_raw), time(23, 59)) if parse_date(expires_raw) else None
            )
        else:
            ann.expires_at = None
        ann.sort_order = int(request.POST.get('sort_order', 0))
        ann.save()
        messages.success(request, 'Announcement updated.')
        return redirect('ecom:cms_announcement_list')
    return render(request, 'ecom/admin/cms/announcement_form.html', {'announcement': ann})


@login_required
@require_POST
def announcement_delete(request, ann_id):
    company = _get_company(request)
    ann = get_object_or_404(Announcement, id=ann_id, company=company)
    ann.delete()
    messages.success(request, 'Announcement deleted.')
    return redirect('ecom:cms_announcement_list')


@login_required
@require_POST
def announcement_toggle(request, ann_id):
    company = _get_company(request)
    ann = get_object_or_404(Announcement, id=ann_id, company=company)
    ann.is_active = not ann.is_active
    ann.save(update_fields=['is_active'])
    return redirect('ecom:cms_announcement_list')


# ──────────────────────────────────────────────────────────
# Blog management
# ──────────────────────────────────────────────────────────

@login_required
def blog_list(request):
    company = _get_company(request)
    posts = BlogPost.objects.filter(company=company)
    return render(request, 'ecom/admin/cms/blog_list.html', {'posts': posts})


@login_required
def blog_create(request):
    company = _get_company(request)
    if request.method == 'POST':
        slug = request.POST.get('slug', '').strip() or slugify(request.POST.get('title', ''))
        post = BlogPost(
            company=company,
            title=request.POST.get('title', '').strip(),
            slug=slug,
            excerpt=request.POST.get('excerpt', '').strip(),
            content=request.POST.get('content', '').strip(),
            author_name=request.POST.get('author_name', '').strip(),
            is_published='is_published' in request.POST,
        )
        published_at = request.POST.get('published_at', '')
        if published_at:
            from django.utils.dateparse import parse_datetime
            post.published_at = parse_datetime(published_at) or timezone.now()
        if 'cover_image' in request.FILES:
            post.cover_image = request.FILES['cover_image']
        post.save()
        messages.success(request, 'Blog post created.')
        return redirect('ecom:cms_blog_list')
    return render(request, 'ecom/admin/cms/blog_form.html', {'post': None})


@login_required
def blog_edit(request, post_id):
    company = _get_company(request)
    post = get_object_or_404(BlogPost, id=post_id, company=company)
    if request.method == 'POST':
        post.title = request.POST.get('title', '').strip()
        post.slug = request.POST.get('slug', '').strip() or slugify(post.title)
        post.excerpt = request.POST.get('excerpt', '').strip()
        post.content = request.POST.get('content', '').strip()
        post.author_name = request.POST.get('author_name', '').strip()
        post.is_published = 'is_published' in request.POST
        published_at = request.POST.get('published_at', '')
        if published_at:
            from django.utils.dateparse import parse_datetime
            post.published_at = parse_datetime(published_at) or timezone.now()
        if 'cover_image' in request.FILES:
            post.cover_image = request.FILES['cover_image']
        post.save()
        messages.success(request, 'Blog post updated.')
        return redirect('ecom:cms_blog_list')
    return render(request, 'ecom/admin/cms/blog_form.html', {'post': post})


@login_required
@require_POST
def blog_delete(request, post_id):
    company = _get_company(request)
    post = get_object_or_404(BlogPost, id=post_id, company=company)
    post.delete()
    messages.success(request, 'Blog post deleted.')
    return redirect('ecom:cms_blog_list')


# ──────────────────────────────────────────────────────────
# Contact message management
# ──────────────────────────────────────────────────────────

@login_required
def contact_list(request):
    company = _get_company(request)
    msgs = ContactMessage.objects.filter(company=company)
    return render(request, 'ecom/admin/cms/contact_list.html', {'messages': msgs})


@login_required
def contact_detail(request, msg_id):
    company = _get_company(request)
    msg = get_object_or_404(ContactMessage, id=msg_id, company=company)
    return render(request, 'ecom/admin/cms/contact_detail.html', {'msg': msg})


@login_required
@require_POST
def contact_mark_read(request, msg_id):
    company = _get_company(request)
    msg = get_object_or_404(ContactMessage, id=msg_id, company=company)
    msg.is_read = True
    msg.save(update_fields=['is_read'])
    return redirect('ecom:cms_contact_detail', msg_id=msg.id)


# ── Product E-Commerce Content ────────────────────────────────────────────────

@login_required
def product_content_list(request):
    company = _get_company(request)
    search = request.GET.get('q', '').strip()
    qs = Product.active_objects.filter(company=company).prefetch_related('images')
    if search:
        from django.db.models import Q
        qs = qs.filter(Q(name__icontains=search) | Q(barcode__icontains=search) | Q(sku__icontains=search))
    return render(request, 'ecom/admin/product_content_list.html', {
        'products': qs,
        'search': search,
    })


@login_required
def product_content_edit(request, product_id):
    company = _get_company(request)
    product = get_object_or_404(Product, id=product_id, company=company)

    from django import forms as django_forms

    class EcomContentForm(django_forms.ModelForm):
        class Meta:
            model = Product
            fields = ['show_on_ecom', 'price', 'compare_at_price', 'short_description', 'ecom_description', 'color']
            widgets = {
                'ecom_description': django_forms.HiddenInput(),
            }

    image_formset = ProductImageFormSet(
        request.POST or None,
        request.FILES or None,
        instance=product,
        prefix='images',
    )
    form = EcomContentForm(request.POST or None, instance=product)

    if request.method == 'POST' and form.is_valid() and image_formset.is_valid():
        form.save()
        image_formset.save()
        messages.success(request, f"E-commerce content updated for '{product.name}'.")
        return redirect('ecom:cms_product_content_edit', product_id=product.id)

    return render(request, 'ecom/admin/product_content_edit.html', {
        'product': product,
        'form': form,
        'image_formset': image_formset,
    })


@require_POST
@login_required
def product_image_delete(request, image_id):
    company = _get_company(request)
    img = get_object_or_404(ProductImage, id=image_id, product__company=company)
    # Refuse to delete the primary image if there are other images
    if img.is_primary and ProductImage.objects.filter(product=img.product).count() > 1:
        return JsonResponse({'ok': False, 'error': 'Set another image as primary first.'}, status=400)
    img.image.delete(save=False)
    img.delete()
    return JsonResponse({'ok': True})
