from ..forms import *
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models.functions import Coalesce
from ...utils.decorator import auth_required
from django.db import transaction
from .stock_disposal_service import post_stock_disposal
from .stock_ledger_service import log_movement, apply_fifo_delta



@auth_required('products.change_package')
def update_package(request, package_id):
    template_name = 'products/package_form.html'
    package = get_object_or_404(Package, pk=package_id)

    if request.method == 'POST':
        form = PackageForm(request.POST, instance=package)
        formset = PackageItemFormSet(
            request.POST,
            instance=package,
            user=request.user,
            prefix='items',
        )

        if form.is_valid() and formset.is_valid():
            package = form.save()
            instances = formset.save(commit=False)

            for obj in formset.deleted_objects:
                obj.delete()

            for instance in instances:
                instance.package = package
                instance.save()

            return redirect('products:update_stock', item_id=product.id)
    else:
        form = PackageForm(instance=package)
        formset = PackageItemFormSet(
            instance=package,
            user=request.user,
            prefix='items',
        )

    return render(request, template_name, {
        'form': form,
        'formset': formset,
        'package': package,
    })

@auth_required('products.change_product')
def update_stock(request, item_id):
    product = get_object_or_404(Product, id=item_id)
    stock_instance, created = ProductStock.objects.get_or_create(product=product)

    if request.method == 'POST':
        form = StockTransactionForm(request.POST ,initial={'product': product})
        if form.is_valid():
            txn_type = form.cleaned_data['transaction_type']
            stock_type = form.cleaned_data['stock_type']
            qty = form.cleaned_data['quantity']
            reason = form.cleaned_data['reason']
            fail = None
            qty_change = 0  # net change in total on-hand; POS<->ECOM transfers are 0

            with transaction.atomic():
                stock_instance = ProductStock.objects.select_for_update().get(pk=stock_instance.pk)

                if stock_type == 'POS':
                    if txn_type == 'ADD':
                        qty_change = qty
                        stock_instance.stock += qty
                    elif txn_type == 'REMOVE':
                        if stock_instance.stock < qty:
                            fail = f"Insufficient POS stock to remove {qty}."
                        else:
                            qty_change = -qty
                            stock_instance.stock -= qty
                    elif txn_type == 'ADJUST':
                        qty_change = qty - stock_instance.stock
                        stock_instance.stock = qty
                else:
                    # E-commerce stock is a pool carved out of POS stock (transfer).
                    if txn_type == 'ADD':
                        if stock_instance.stock < qty:
                            fail = f"Insufficient POS stock ({stock_instance.stock}) to transfer {qty} to E-commerce."
                        else:
                            stock_instance.stock -= qty
                            stock_instance.ecom_stock += qty
                    elif txn_type == 'REMOVE':
                        if stock_instance.ecom_stock < qty:
                            fail = f"Insufficient E-commerce stock ({stock_instance.ecom_stock}) to return {qty} to POS."
                        else:
                            stock_instance.ecom_stock -= qty
                            stock_instance.stock += qty
                    elif txn_type == 'ADJUST':
                        diff = qty - stock_instance.ecom_stock
                        if diff > 0 and stock_instance.stock < diff:
                            fail = f"Insufficient POS stock to adjust E-commerce to {qty}."
                        else:
                            stock_instance.stock -= diff
                            stock_instance.ecom_stock = qty

                if not fail:
                    stock_instance.save()
                    transfer = stock_type == 'ECOM'
                    log_movement(
                        product, transaction_type=txn_type, stock_type=stock_type, quantity=qty,
                        qty_change=qty_change, user=request.user, reason=reason,
                        unit_cost=product.cost_price if transfer else apply_fifo_delta(product, qty_change),
                    )

            if fail:
                messages.error(request, fail)
                return redirect('products:update_stock', item_id=product.id)

            messages.success(request, f"Stock updated for {product.name}.")
            return redirect('products:update_stock', item_id=product.id)
    else:
        form = StockTransactionForm(initial={'product': product})

    return render(request, 'products/update_stock.html', {
        'form': form,
        'product': product,
        'stock': stock_instance,
        'enable_ecom': getattr(product.company, 'enable_ecom', False) if product.company else False,
    })


@auth_required('products.change_product')
def dispose_stock(request, item_id):
    """NFRS 2 (IAS 2) inventory write-off — posts a loss journal via post_stock_disposal()."""
    product = get_object_or_404(Product, id=item_id)
    stock_instance, _ = ProductStock.objects.get_or_create(product=product)

    if request.method == 'POST':
        form = StockDisposalForm(request.POST)
        if form.is_valid():
            try:
                post_stock_disposal(
                    product=product,
                    quantity=form.cleaned_data['quantity'],
                    disposal_reason=form.cleaned_data['disposal_reason'],
                    stock_type=form.cleaned_data['stock_type'],
                    reason=form.cleaned_data['reason'],
                    posted_by=request.user,
                )
                messages.success(request, f"{form.cleaned_data['quantity']} unit(s) of {product.name} written off.")
                return redirect('products:update_stock', item_id=product.id)
            except ValueError as e:
                messages.error(request, str(e))
                return redirect('products:dispose_stock', item_id=product.id)
    else:
        form = StockDisposalForm()

    return render(request, 'products/dispose_stock.html', {
        'form': form,
        'product': product,
        'stock': stock_instance,
        'disposal_reasons': StockTransaction.DISPOSAL_REASON_CHOICES,
        'enable_ecom': getattr(product.company, 'enable_ecom', False) if product.company else False,
    })


@auth_required('products.change_product')
def bulk_write_off(request):
    """Write off stock for multiple products in one submission (NFRS 2 write-off per line)."""
    company = getattr(request.user, 'company', None)

    if request.method == 'POST':
        product_ids = request.POST.getlist('product_id[]')
        quantities = request.POST.getlist('quantity[]')
        stock_types = request.POST.getlist('stock_type[]')
        disposal_reasons = request.POST.getlist('disposal_reason[]')
        reasons = request.POST.getlist('reason[]')

        rows = []
        errors = []
        for i, product_id in enumerate(product_ids):
            if not product_id:
                continue
            qty_raw = quantities[i] if i < len(quantities) else ''
            if not qty_raw.strip():
                continue
            try:
                qty = int(qty_raw)
            except ValueError:
                errors.append(f"Row {i + 1}: quantity must be a whole number.")
                continue
            rows.append({
                'product_id': product_id,
                'quantity': qty,
                'stock_type': stock_types[i] if i < len(stock_types) else 'POS',
                'disposal_reason': disposal_reasons[i] if i < len(disposal_reasons) else 'OTHER',
                'reason': reasons[i] if i < len(reasons) else '',
            })

        if not rows and not errors:
            errors.append("Add at least one product to write off.")

        if not errors:
            try:
                with transaction.atomic():
                    products_written_off = 0
                    for row in rows:
                        product = get_object_or_404(Product, id=row['product_id'])
                        post_stock_disposal(
                            product=product,
                            quantity=row['quantity'],
                            disposal_reason=row['disposal_reason'],
                            stock_type=row['stock_type'],
                            reason=row['reason'],
                            posted_by=request.user,
                        )
                        products_written_off += 1
                messages.success(request, f"{products_written_off} product(s) written off successfully.")
                return redirect('products:disposal_history')
            except ValueError as e:
                errors.append(str(e))

        for err in errors:
            messages.error(request, err)
        return redirect('products:bulk_write_off')

    products_qs = Product.active_objects.filter(is_service=False).prefetch_related('productstock')
    if company:
        products_qs = products_qs.filter(company=company)
    products_qs = products_qs.order_by('name')

    return render(request, 'products/bulk_write_off.html', {
        'products': products_qs,
        'disposal_reasons': StockTransaction.DISPOSAL_REASON_CHOICES,
    })


@auth_required('products.view_product')
def disposal_history(request):
    company = request.user.company if hasattr(request.user, 'company') else None
    disposals = StockTransaction.objects.filter(transaction_type='DISPOSAL').select_related(
        'product', 'user', 'journal_entry'
    ).order_by('-created_at')
    if not request.user.is_superuser and company:
        disposals = disposals.filter(product__company=company)

    return render(request, 'products/disposal_history.html', {
        'disposals': disposals,
    })


@auth_required('products.change_category')
def edit_category(request, category_id):
    category = get_object_or_404(Category, id=category_id)
    if request.method == 'POST':
        form = CategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            messages.success(request, "Category updated successfully")
            return redirect('products:update_stock', item_id=product.id) # Redirect to inventory or category list
    else:
        form = CategoryForm(instance=category)

    context = {
        'form': form,
        'category': category,
    }
    return render(request, 'products/edit_category.html', context)


@auth_required('products.change_category')
def edit_category_type(request, id):
    categorytype = get_object_or_404(CategoryType, id=id)
    if request.method == 'POST':
        form = CategoryForm(request.POST, instance=categorytype)
        if form.is_valid():
            form.save()
            messages.success(request, "Category Type updated successfully")
            return redirect('products:update_stock', item_id=product.id)
    else:
        form = CategoryTypeForm(instance=categorytype)

    context = {
        'form': form,
        'categorytype': categorytype,
    }
    return render(request, 'products/edit_category.html', context)


@auth_required('products.change_product')
def edit_item(request, id):
    product = get_object_or_404(Product, id=id)
    category_type = product.category.type if product.category else None

    form = ItemForm(request.POST or None, instance=product, user=request.user)

    if request.method == 'POST':
        if form.is_valid():
            with transaction.atomic():
                form.save()

                new_qty = form.cleaned_data.get('stock_quantity')
                if new_qty is not None:
                    stock_instance, _ = ProductStock.objects.get_or_create(product=product)
                    diff = new_qty - stock_instance.stock
                    if diff != 0:
                        log_movement(
                            product, transaction_type='ADJUST', stock_type='POS', quantity=new_qty,
                            qty_change=diff, user=request.user,
                            reason='Stock quantity adjusted from item edit form',
                            unit_cost=apply_fifo_delta(product, diff),
                        )
                        stock_instance.stock = new_qty
                        stock_instance.save(update_fields=['stock', 'updated_at'])

            messages.success(request, f"'{product.name}' updated successfully")
            return redirect('products:inventory_management')

    context = {
        'form': form,
        'item_form_sections': item_form_sections(form, exclude={'category_type'}),
        'product': product,
        'category_type': category_type,
        'enable_ecom': getattr(product.company, 'enable_ecom', False) if product.company else False,
    }
    return render(request, 'products/edit_item.html', context)