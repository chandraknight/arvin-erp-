from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.company.models import Company
from apps.ecom import media_services


def _get_company(request):
    return request.user.profile.company if hasattr(request.user, 'profile') else Company.objects.first()


@login_required
def media_library(request):
    company = _get_company(request)
    kind = request.GET.get('kind') or None
    q = request.GET.get('q') or None
    folder = request.GET.get('folder') or None
    items = media_services.collect_media(company, kind=kind, q=q, folder=folder)
    items.sort(key=lambda i: (i['is_webp'], i['label'].lower()))
    folders = media_services.get_folders(company)
    return render(request, 'ecom/admin/media/library.html', {
        'items': items,
        'kinds': media_services.MEDIA_KINDS,
        'active_kind': kind,
        'active_folder': folder,
        'folders': folders,
        'q': q or '',
        'total_size': sum(i['size'] for i in items),
        'unoptimized_count': sum(1 for i in items if not i['is_webp']),
    })


def _redirect_back(request):
    params = []
    if request.POST.get('kind'):
        params.append(f"kind={request.POST['kind']}")
    if request.POST.get('q'):
        params.append(f"q={request.POST['q']}")
    url = reverse('ecom:media_library')
    return redirect(url + ('?' + '&'.join(params) if params else ''))


@login_required
@require_POST
def media_optimize(request):
    company = _get_company(request)
    key = request.POST.get('key')
    if key:
        instance, field_name = media_services.resolve_media_target(company, key)
        result = media_services.optimize_image_field(instance, field_name)
        if result:
            messages.success(request, f'Optimized — saved {(result[0] - result[1]) / 1024:.0f} KB.')
        else:
            messages.info(request, 'Already optimized or could not be converted.')
    else:
        count, saved = media_services.optimize_all_media(company, kind=request.POST.get('kind') or None)
        messages.success(request, f'Optimized {count} image(s) — saved {saved / 1024:.0f} KB.')
    return _redirect_back(request)


@login_required
@require_POST
def media_replace(request):
    company = _get_company(request)
    uploaded = request.FILES.get('file')
    if not uploaded:
        messages.error(request, 'No file selected.')
        return _redirect_back(request)
    instance, field_name = media_services.resolve_media_target(company, request.POST['key'])
    media_services.replace_media_file(instance, field_name, uploaded)
    messages.success(request, 'Image replaced and optimized.')
    return _redirect_back(request)


@login_required
@require_POST
def media_delete(request):
    company = _get_company(request)
    instance, field_name = media_services.resolve_media_target(company, request.POST['key'])
    try:
        media_services.delete_media_file(instance, field_name)
        messages.success(request, 'Image removed.')
    except ValueError as e:
        messages.error(request, str(e))
    return _redirect_back(request)


@login_required
@require_POST
def media_upload(request):
    company = _get_company(request)
    uploaded = request.FILES.get('file')
    if not uploaded:
        messages.error(request, 'No file selected.')
        return redirect(reverse('ecom:media_library') + '?kind=upload')
    label = request.POST.get('label', '').strip() or uploaded.name
    folder = request.POST.get('folder', 'general')
    media_services.ensure_folder(company, folder)
    media_services.upload_media_file(company, uploaded, label, folder)
    messages.success(request, f'"{label}" uploaded.')
    url = reverse('ecom:media_library') + f'?kind=upload&folder={folder}'
    return redirect(url)


@login_required
@require_POST
def media_folder_create(request):
    company = _get_company(request)
    name = request.POST.get('name', '').strip()
    if name:
        media_services.ensure_folder(company, name)
        messages.success(request, f'Folder "{name}" created.')
    return redirect(reverse('ecom:media_library') + f'?kind=upload&folder={name}')


@login_required
@require_POST
def media_folder_delete(request):
    company = _get_company(request)
    name = request.POST.get('name', '').strip()
    if name and name != 'general':
        media_services.delete_folder(company, name)
        messages.success(request, f'Folder "{name}" deleted. Files moved to General.')
    return redirect(reverse('ecom:media_library') + '?kind=upload')
