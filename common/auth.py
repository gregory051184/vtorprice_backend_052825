from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from rest_framework import exceptions

User = get_user_model()


class BaseModelBackend(ModelBackend):
    def user_can_authenticate(self, user):
        can_authenticate = super(BaseModelBackend, self).user_can_authenticate(
            user
        )
        if can_authenticate and user.is_superuser:
            return True
        return can_authenticate and getattr(user, "phone_confirmed", False)

    def get_user(self, pk):
        try:
            return User.objects.get(pk=pk)
        except User.DoesNotExist:
            raise exceptions.NotFound(
                {"detail": "Пользователь не зарегистрирован"}
            )


class AuthModelBackend(BaseModelBackend):
    def authenticate(self, request, **credentials):
        phone = credentials.get("phone")
        password = credentials.get("password")

        if not phone or not password:
            return None

        try:
            user = User.objects.get(phone=phone)
        except User.DoesNotExist:
            raise exceptions.NotFound(
                {"detail": "Пользователь не зарегистрирован"}
            )
        else:
            if user.password != password:
                raise exceptions.ValidationError(
                    {"detail": "Не верный пароль"}
                )
            return user
