from django.core.exceptions import PermissionDenied


def developer(user):
    if not user.is_authenticated or user.role != "DEVELOPER":
        raise PermissionDenied


def scoped(queryset, user, path="client_id"):
    if user.role == "DEVELOPER":
        return queryset
    return queryset.filter(**{path: user.client_id})
