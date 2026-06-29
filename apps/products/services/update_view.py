from ..forms import *
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models.functions import Coalesce
from ...utils.decorator import auth_required
from django.db import transaction



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
            stock_transaction_log = form.save(commit=False)
            stock_transaction_log.product = product  # assign from URL
            stock_transaction_log.user = request.user
            stock_transaction_log.save()

            # Logic for POS Stock (Master Pool)
            if stock_transaction_log.stock_type == 'POS':
                if stock_transaction_log.transaction_type == 'ADD':
                    stock_instance.stock += stock_transaction_log.quantity
                elif stock_transaction_log.transaction_type == 'REMOVE':
                    if stock_instance.stock < stock_transaction_log.quantity:
                        messages.error(request, f"Insufficient POS stock to remove {stock_transaction_log.quantity}.")
                        return redirect('products:update_stock', item_id=product.id)
                    stock_instance.stock -= stock_transaction_log.quantity
                elif stock_transaction_log.transaction_type == 'ADJUST':
                    stock_instance.stock = stock_transaction_log.quantity

            # Logic for E-commerce Stock (Transfer from/to POS Pool)
            elif stock_transaction_log.stock_type == 'ECOM':
                qty = stock_transaction_log.quantity
                
                if stock_transaction_log.transaction_type == 'ADD':
                    # Moving from POS to ECOM
                    if stock_instance.stock < qty:
                        messages.error(request, f"Insufficient POS stock ({stock_instance.stock}) to transfer {qty} to E-commerce.")
                        return redirect('products:update_stock', item_id=product.id)
                    stock_instance.stock -= qty
                    stock_instance.ecom_stock += qty

                elif stock_transaction_log.transaction_type == 'REMOVE':
                    # Moving from ECOM back to POS
                    if stock_instance.ecom_stock < qty:
                        messages.error(request, f"Insufficient E-commerce stock ({stock_instance.ecom_stock}) to return {qty} to POS.")
                        return redirect('products:update_stock', item_id=product.id)
                    stock_instance.ecom_stock -= qty
                    stock_instance.stock += qty

                elif stock_transaction_log.transaction_type == 'ADJUST':
                    # Adjusting ECOM specifically, balancing with POS
                    diff = qty - stock_instance.ecom_stock
                    if diff > 0: # Need more for ECOM
                        if stock_instance.stock < diff:
                            messages.error(request, f"Insufficient POS stock to adjust E-commerce to {qty}.")
                            return redirect('products:update_stock', item_id=product.id)
                        stock_instance.stock -= diff
                    else: # Returning surplus to POS
                        stock_instance.stock += abs(diff)
                    stock_instance.ecom_stock = qty
            
            stock_instance.save()

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

    form = ItemForm(request.POST or None, instance=product, user=request.user, category_type=category_type)

    if request.method == 'POST':
        if form.is_valid():
            form.save()
            messages.success(request, f"'{product.name}' updated successfully")
            return redirect('products:add_item')

    context = {
        'form': form,
        'product': product,
        'category_type': category_type,
        'enable_ecom': getattr(product.company, 'enable_ecom', False) if product.company else False,
    }
    return render(request, 'products/edit_item.html', context)