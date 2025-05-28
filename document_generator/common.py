from document_generator.generators.document_generators import BaseGenerator
from document_generator.models import GeneratedDocumentModel


def get_or_generate_document(generator: BaseGenerator, document_filter_kwargs):
    if not GeneratedDocumentModel.objects.filter(
        **document_filter_kwargs
    ).exists():
        document_path = generator.replace_all_and_save()
        document = GeneratedDocumentModel.objects.create(
            **document_filter_kwargs, document=document_path
        )
        return document
    return GeneratedDocumentModel.objects.filter(
        **document_filter_kwargs
    ).get()
