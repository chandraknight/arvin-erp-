from django.contrib import messages

from ..models import *
from ...utils.decorator import auth_required
from django.shortcuts import render, redirect, get_object_or_404


@auth_required('accounts.delete_user')
def user_delete(request, id):
    user_to_delete = get_object_or_404(User, pk=id)

    if request.method == 'POST':
        user_to_delete.soft_delete(deleted_by=request.user.id)
        messages.success(request, f"User {user_to_delete.email} deleted successfully!")
        return redirect('accounts:user_list')

    return redirect('accounts:user_list')

