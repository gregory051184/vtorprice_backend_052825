from rest_framework import permissions

from logistics.models import Contractor
from user.models import UserRole


class ContragentsAccessPermissions(permissions.BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return not user.is_anonymous and user.role >= UserRole.LOGIST

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_anonymous or user.role < UserRole.LOGIST:
            return False
        if isinstance(obj, Contractor):
            return user.company == obj.created_by.company
        if isinstance(obj, ContractorDocuments):
            return user.company == obj.contractor.created_by.company


class LogisticsOffersPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        # TODO: При добавлении возможности добавлять в команду Не админов пересмотреть флоу
        user = request.user

        return not user.is_anonymous
