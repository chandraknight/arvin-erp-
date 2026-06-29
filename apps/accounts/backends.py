from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.hashers import check_password
from .models import User


class AuthBackend(ModelBackend):
    def authenticate(self, request, email=None, password=None, **kwargs):
        try:
            user = User.active_objects.get(email=email)
        except User.DoesNotExist:
            return None

        if user.is_active and check_password(password, user.password):
            return user
        return None
      