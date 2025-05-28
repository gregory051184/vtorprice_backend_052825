from django.contrib.auth.models import Permission
from django.core.cache import cache


def get_all_permissions():

    all_permissions = cache.get("all_permissions", None)
    if not all_permissions:
        all_permissions = set(
            [
                p.content_type.app_label + "." + p.codename
                for p in Permission.objects.all()
            ]
        )
        cache.set("all_permissions", all_permissions)

    return all_permissions
