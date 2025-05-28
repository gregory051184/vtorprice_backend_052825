from drf_yasg import inspectors
from drf_yasg.app_settings import swagger_settings
from drf_yasg.inspectors import ChoiceFieldInspector


class BaseAutoSchema(inspectors.SwaggerAutoSchema):
    field_inspectors = [
        ChoiceFieldInspector
    ] + swagger_settings.DEFAULT_FIELD_INSPECTORS

    def get_parser_classes(self):
        """Get the parser classes of this view by calling `get_parsers`.

        :return: parser classes
        :rtype: list[type[rest_framework.parsers.BaseParser]]
        """
        if hasattr(self.view, "yasg_parser_classes"):
            return self.view.yasg_parser_classes

        return super().get_parser_classes()
