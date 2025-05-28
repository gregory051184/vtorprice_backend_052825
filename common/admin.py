from django.contrib import admin
from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.forms import Textarea


class BaseModelAdmin(admin.ModelAdmin):
    def get_list_filter(self, request):
        list_filter = [item for item in self.list_filter]
        list_filter.append("is_deleted")
        return list_filter

    def get_search_fields(self, request):
        try:
            self.model._meta.get_field("name")
        except FieldDoesNotExist:
            return self.search_fields
        else:
            search_fields = [item for item in self.search_fields]
            if "name" not in search_fields:
                search_fields.append("name")
            return search_fields

    formfield_overrides = {
        models.TextField: {"widget": Textarea(attrs={"rows": 2, "cols": 40})},
    }
