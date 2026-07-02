from ..forms import *
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models.functions import Coalesce
from ...utils.decorator import auth_required
from django.db import transaction
import logging
from django.template.loader import render_to_string
from django.forms import formset_factory, modelformset_factory


@auth_required('products.add_category')
def add_category(request):
    # Guard: category type must exist before creating a category
    ct_qs = (
        CategoryType.active_objects.all()
        if request.user.is_superuser
        else CategoryType.active_objects.filter(company=request.user.company)
    )
    if not ct_qs.exists():
        messages.warning(
            request,
            "Create a Category Type first — categories must belong to a type."
        )
        return redirect('products:add_category_type')

    page_number = request.GET.get('page', 1)
    if request.method == 'POST':
        form = CategoryForm(request.POST, user=request.user)
        if form.is_valid():
            category = form.save(commit=False)
            if request.user.company:
                category.company = request.user.company
            category.save()
            messages.success(request, "Category added successfully")
            return redirect('products:add_category')
    else:
        form = CategoryForm(user=request.user)

    if request.user.is_superuser:
        category_list = Category.active_objects.all().annotate(
            sort_time=Coalesce('updated_at', 'created_at')
        ).order_by('-sort_time')
    else:
        category_list = Category.active_objects.filter(company=request.user.company).annotate(
            sort_time=Coalesce('updated_at', 'created_at')
        ).order_by('-sort_time')

    try:
        paginate_by = int(request.GET.get('paginate_by', 10))
    except (ValueError, TypeError):
        paginate_by = 5

    paginator = Paginator(category_list, paginate_by)
    page_number = request.GET.get('page')

    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    context = {
        'form': form,
'object_list': page_obj.object_list,
        'page_obj': page_obj,
        'paginate_by': paginate_by
    }
    return render(request, 'products/add_category.html', context)


@auth_required('products.add_product')
def add_item(request):
    company = request.user.company if not request.user.is_superuser else None

    # Guard: must have at least one CategoryType before adding a product
    ct_qs = (
        CategoryType.active_objects.all()
        if request.user.is_superuser
        else CategoryType.active_objects.filter(company=company)
    )
    if not ct_qs.exists():
        messages.warning(
            request,
            "You need to create a Category Type before adding products. "
            "Start here — you'll be guided back to add your product once it's done."
        )
        return redirect('products:add_category_type')

    # Guard: must have at least one Category before adding a product
    cat_qs = (
        Category.active_objects.all()
        if request.user.is_superuser
        else Category.active_objects.filter(company=company)
    )
    if not cat_qs.exists():
        messages.warning(
            request,
            "You need to create a Category before adding products. "
            "Create one here — you'll be brought back to add your product once it's ready."
        )
        return redirect('products:add_category')

    category_type_id = request.GET.get('category_type') or request.POST.get('category_type')
    category_type = None
    if category_type_id:
        try:
            category_type = CategoryType.active_objects.get(id=category_type_id)
        except CategoryType.DoesNotExist:
            pass

    form = ItemForm(request.POST or None, user=request.user, category_type=category_type)

    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            product = form.save(commit=False)
            product.company = request.user.company if request.user.company else None
            product.save()

            ProductStock.objects.create(
                product=product,
                stock=0,
                minimum_stock=0
            )
            messages.success(request, f"Added '{product.name}' to inventory.")
            return redirect('products:add_item')
    else:
        if request.method != 'POST':
            form = ItemForm(user=request.user)

    if request.user.is_superuser:
        product_list = Product.active_objects.all().annotate(
            sort_time=Coalesce('updated_at', 'created_at')
        ).order_by('-sort_time')
    else:
        product_list = Product.active_objects.filter(company=request.user.company).annotate(
            sort_time=Coalesce('updated_at', 'created_at')
        ).order_by('-sort_time')

    try:
        paginate_by = int(request.GET.get('paginate_by', 5))
    except (ValueError, TypeError):
        paginate_by = 5

    paginator = Paginator(product_list, paginate_by)
    page_number = request.GET.get('page')
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)
    company = getattr(request.user, 'company', None)
    context = {
        'form': form,
        'object_list': page_obj.object_list,
        'page_obj': page_obj,
        'paginate_by': paginate_by,
        'enable_ecom': getattr(company, 'enable_ecom', False) if company else False,
    }

    return render(request, 'products/add_item.html', context)


@auth_required('products.add_package')
def create_package(request):
    template_name = 'products/package_form.html'
    package_instance = Package()

    form = PackageForm(request.POST or None, instance=package_instance, prefix='main')
    formset = PackageItemFormSet(request.POST or None, instance=package_instance, prefix='items', user=request.user)
    if request.method == 'POST':
        if form.is_valid() and formset.is_valid():
            package = form.save(commit=False)
            package.company = request.user.company
            package.created_by = request.user
            package.save()
            formset.save()
            return redirect('products:inventory_management')

    context = {'form': form, 'formset': formset}
    return render(request, template_name, context)



@auth_required('products.add_categorytype')
def create_categorytype(request):
    form = CategoryTypeForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            categorytype = form.save(commit=False)
            categorytype.company = request.user.company
            categorytype.save()

            return redirect('products:add_category_type')
    else:
        form = CategoryTypeForm()

    if request.user.is_superuser:
        categorytype_list = CategoryType.active_objects.all().annotate(
            sort_time=Coalesce('updated_at', 'created_at')
        ).order_by('-sort_time')
    else:
        categorytype_list = CategoryType.active_objects.filter(company=request.user.company).annotate(
            sort_time=Coalesce('updated_at', 'created_at')
        ).order_by('-sort_time')

    try:
        paginate_by = int(request.GET.get('paginate_by', 5))
    except (ValueError, TypeError):
        paginate_by = 5

    paginator = Paginator(categorytype_list, paginate_by)
    page_number = request.GET.get('page')
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)
    context = {
        'form': form,
        'object_list': page_obj.object_list,
        'page_obj': page_obj,
        'paginate_by': paginate_by
    }

    return render(request, 'products/add_category_type.html', context)
