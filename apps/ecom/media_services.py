"""
Unified media library for the ecom storefront.
Aggregates images scattered across ProductImage, Category, SiteSettings,
HeroBanner and BlogPost into one browsable, optimizable collection.
"""
import io
import os

from PIL import Image as PilImage, ImageOps
from django.core.files.base import ContentFile

from apps.ecom.models import SiteSettings, HeroBanner, BlogPost, MediaFile, MediaFolder
from apps.products.models import Category, ProductImage

MEDIA_KINDS = [
    ('upload', 'Uploaded Files'),
    ('product', 'Products'),
    ('category', 'Categories'),
    ('branding', 'Logo & Favicon'),
    ('banner', 'Banners'),
    ('blog', 'Blog'),
]


def _item(kind, instance, field_name, label, can_delete=True):
    field = getattr(instance, field_name)
    if not field or not field.name:
        return None
    try:
        size = field.storage.size(field.name)
    except Exception:
        size = 0
    return {
        'key': f'{kind}:{instance.pk}:{field_name}',
        'kind': kind,
        'label': label,
        'url': field.url,
        'name': os.path.basename(field.name),
        'size': size,
        'is_webp': field.name.lower().endswith('.webp'),
        'can_delete': can_delete,
    }


def collect_media(company, kind=None, q=None, folder=None):
    items = []

    if kind in (None, 'upload'):
        qs = MediaFile.objects.filter(company=company)
        if folder:
            qs = qs.filter(folder=folder)
        if q:
            qs = qs.filter(label__icontains=q)
        for mf in qs:
            if not mf.file or not mf.file.name:
                continue
            try:
                size = mf.file.storage.size(mf.file.name)
            except Exception:
                size = 0
            items.append({
                'key': f'upload:{mf.pk}:file',
                'kind': 'upload',
                'label': mf.label or os.path.basename(mf.file.name),
                'url': mf.file.url,
                'name': os.path.basename(mf.file.name),
                'size': size,
                'is_webp': mf.file.name.lower().endswith('.webp'),
                'can_delete': True,
                'folder': mf.folder,
            })

    if kind in (None, 'product'):
        qs = ProductImage.objects.filter(product__company=company).select_related('product')
        if q:
            qs = qs.filter(product__name__icontains=q)
        items += [_item('product', pi, 'image', pi.product.name) for pi in qs]

    if kind in (None, 'category'):
        qs = Category.objects.filter(company=company).exclude(ecom_image='').exclude(ecom_image__isnull=True)
        if q:
            qs = qs.filter(name__icontains=q)
        items += [_item('category', c, 'ecom_image', c.name) for c in qs]

    if kind in (None, 'branding'):
        settings = SiteSettings.objects.filter(company=company).first()
        if settings and (not q or q.lower() in 'logo favicon'):
            items.append(_item('branding', settings, 'logo', 'Site Logo'))
            items.append(_item('branding', settings, 'favicon', 'Favicon'))

    if kind in (None, 'banner'):
        qs = HeroBanner.objects.filter(company=company)
        if q:
            qs = qs.filter(title__icontains=q)
        items += [_item('banner', b, 'image', b.title or 'Banner') for b in qs]

    if kind in (None, 'blog'):
        qs = BlogPost.objects.filter(company=company)
        if q:
            qs = qs.filter(title__icontains=q)
        items += [_item('blog', p, 'cover_image', p.title) for p in qs]

    return [i for i in items if i]


def resolve_media_target(company, key):
    kind, pk, field_name = key.split(':')
    lookups = {
        'upload': (MediaFile, {'company': company}, {'file'}),
        'product': (ProductImage, {'product__company': company}, {'image'}),
        'category': (Category, {'company': company}, {'ecom_image'}),
        'branding': (SiteSettings, {'company': company}, {'logo', 'favicon'}),
        'banner': (HeroBanner, {'company': company}, {'image'}),
        'blog': (BlogPost, {'company': company}, {'cover_image'}),
    }
    model, scope, allowed_fields = lookups[kind]
    if field_name not in allowed_fields:
        raise ValueError(f'Invalid field {field_name}')
    return model.objects.get(pk=pk, **scope), field_name


def upload_media_file(company, uploaded_file, label, folder):
    folder = (folder or 'general').strip() or 'general'
    mf = MediaFile.objects.create(company=company, label=label or '', folder=folder)
    mf.file.save(uploaded_file.name, uploaded_file, save=True)
    optimize_image_field(mf, 'file')
    return mf


def get_folders(company):
    return list(MediaFolder.objects.filter(company=company).values_list('name', flat=True))


def ensure_folder(company, name):
    name = name.strip()
    if name:
        MediaFolder.objects.get_or_create(company=company, name=name)


def delete_folder(company, name):
    MediaFolder.objects.filter(company=company, name=name).delete()
    MediaFile.objects.filter(company=company, folder=name).update(folder='general')


def optimize_image_field(instance, field_name):
    """Convert the image to WebP in place. Returns (old_size, new_size), or None if skipped."""
    field = getattr(instance, field_name)
    if not field or not field.name or field.name.lower().endswith('.webp'):
        return None
    storage = field.storage
    old_name = field.name
    try:
        old_size = storage.size(old_name)
        with storage.open(old_name) as f, PilImage.open(f) as img:
            try:
                img = ImageOps.exif_transpose(img)
            except Exception:
                pass
            if img.mode in ('RGBA', 'LA'):
                background = PilImage.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1])
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            buf = io.BytesIO()
            img.save(buf, format='WEBP', quality=82, method=6)
        buf.seek(0)
        new_name = os.path.splitext(old_name)[0] + '.webp'
        saved_name = storage.save(new_name, ContentFile(buf.read()))
        storage.delete(old_name)
        type(instance).objects.filter(pk=instance.pk).update(**{field_name: saved_name})
        return old_size, storage.size(saved_name)
    except Exception:
        return None


def optimize_all_media(company, kind=None):
    """Optimize every non-WebP image. Returns (converted_count, bytes_saved)."""
    converted, saved = 0, 0
    for item in collect_media(company, kind=kind):
        if item['is_webp']:
            continue
        instance, field_name = resolve_media_target(company, item['key'])
        result = optimize_image_field(instance, field_name)
        if result:
            converted += 1
            saved += result[0] - result[1]
    return converted, saved


def replace_media_file(instance, field_name, uploaded_file):
    """Swap the target's image for an uploaded file, then optimize it."""
    field = getattr(instance, field_name)
    if field and field.name:
        field.storage.delete(field.name)
    field.save(uploaded_file.name, uploaded_file, save=True)
    instance.refresh_from_db()
    optimize_image_field(instance, field_name)


def delete_media_file(instance, field_name):
    if isinstance(instance, MediaFile):
        instance.file.delete(save=False)
        instance.delete()
        return
    if isinstance(instance, ProductImage):
        if instance.is_primary and ProductImage.objects.filter(product=instance.product).count() > 1:
            raise ValueError('Set another image as primary first.')
        instance.image.delete(save=False)
        instance.delete()
        return
    field = getattr(instance, field_name)
    field.delete(save=True)
