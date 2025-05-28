from common.serializers import NonNullDynamicFieldsModelSerializer
from document_generator.models import GeneratedDocumentModel


class GeneratedDocumentSerializer(NonNullDynamicFieldsModelSerializer):
    class Meta:
        model = GeneratedDocumentModel
