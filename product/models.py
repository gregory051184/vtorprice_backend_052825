from bulk_update_or_create import BulkUpdateOrCreateQuerySet
from django.db import models
from mptt.fields import TreeForeignKey
from mptt.managers import TreeManager
from mptt.models import MPTTModel

from common.models import BaseNameModel, BaseNameDescModel
from exchange.models import ApplicationStatus, DealType, DealStatus


class CategoryManager(TreeManager):
    def viewable(self):
        queryset = self.get_queryset().filter(level=0)
        return queryset


class RecyclablesCategory(MPTTModel, BaseNameModel):
    parent = TreeForeignKey(
        "self",
        verbose_name="Родительская категория",
        on_delete=models.CASCADE,
        related_name="subcategories",
        null=True,
        blank=True,
    )
    image = models.ImageField("Изображение", null=True, blank=True)

    objects = CategoryManager()

    class Meta:
        verbose_name = "Категория вторсырья"
        verbose_name_plural = "Категории вторсырья"
        db_table = "recyclables_categories"

    class MPTTMeta:
        order_insertion_by = ["name"]


class EquipmentCategory(MPTTModel, BaseNameModel):
    parent = TreeForeignKey(
        "self",
        verbose_name="Родительская категория",
        on_delete=models.CASCADE,
        related_name="subcategories",
        null=True,
        blank=True,
    )
    image = models.ImageField("Изображение", null=True, blank=True)
    objects = CategoryManager()

    class Meta:
        verbose_name = "Категория оборудования"
        verbose_name_plural = "Категории оборудования"
        db_table = "equipment_categories"

    class MPTTMeta:
        order_insertion_by = ["name"]


class RecyclablesQuerySet(BulkUpdateOrCreateQuerySet, models.QuerySet):

    def annotate_applications(self, urgency_type=None, *args, **kwargs):
        query = [("applications__status", ApplicationStatus.PUBLISHED)]
        applications_query = [("status", ApplicationStatus.PUBLISHED)]

        if urgency_type:
            query.append(("applications__urgency_type", urgency_type))
            applications_query.append(("urgency_type", urgency_type))
        query = dict(query)

        sales_applications_count = models.Count(
            "applications",
            filter=models.Q(applications__deal_type=DealType.SELL, **query),
        )
        purchase_applications_count = models.Count(
            "applications",
            filter=models.Q(applications__deal_type=DealType.BUY, **query),
        )
        applications = self.model.applications.field.model.objects.filter(
            recyclables=models.OuterRef("pk"), **dict(applications_query)
        )

        return self.annotate(
            sales_applications_count=sales_applications_count,
            purchase_applications_count=purchase_applications_count,
            published_date=models.Subquery(
                applications.order_by("-created_at").values("created_at")[:1]
            ),
            lot_size=models.Subquery(
                applications.order_by("lot_size").values("lot_size")[:1]
            ),
            # ДОБАВИЛ
            price=models.Subquery(
                applications.order_by("price").values("price")[:1]
            ),
            recyclables_id=models.Subquery(
                applications.order_by("recyclables_id").values("recyclables_id")[:1]
            )
        )  # .order_by('recyclables_id')

    def ordering_applications(self, ordering, urgency_type=None, page=0, size=0, *args, **kwargs):
        if ordering == 'price' or ordering == '-price':
            g = self.annotate_applications(urgency_type=int(urgency_type))
            return g.order_by(ordering)

        if ordering == 'category' or ordering == '-category':
            g = self.annotate_applications(urgency_type=int(urgency_type))
            return g.order_by('category' if ordering == 'recyclables_id' else '-recyclables_id')

        if ordering == 'purchaseApplicationsCount' or ordering == '-purchaseApplicationsCount':
            g = self.annotate_applications(urgency_type=int(urgency_type))
            return g.order_by(
                'purchase_applications_count' if ordering == 'purchaseApplicationsCount' else '-purchase_applications_count')

        if ordering == 'salesApplicationsCount' or ordering == '-salesApplicationsCount':
            g = self.annotate_applications(urgency_type=int(urgency_type))
            return g.order_by(
                'sales_applications_count' if ordering == 'salesApplicationsCount' else '-sales_applications_count')

        if ordering == 'lotSize' or ordering == '-lotSize':
            g = self.annotate_applications(urgency_type=int(urgency_type))
            return g.order_by('lot_size' if ordering == 'lotSize' else '-lot_size')

        if ordering == 'publishedDate' or ordering == '-publishedDate':
            g = self.annotate_applications(urgency_type=int(urgency_type))
            return g.order_by('published_date' if ordering == 'publishedDate' else '-published_date')

    def recyclables_generate_offers(self, category=None):

        companies_count = models.Count('applications',
                                       filter=models.Q(applications__deals__status=DealStatus.COMPLETED))

        return self.annotate(
            companies_count=companies_count,
        )

    def recyclables_app_generate_offers(self, category=None):
        companies_buy_app_count = models.Count('applications',
                                               filter=models.Q(applications__id__gte=0, applications__deal_type=DealType.BUY))

        return self.annotate(
            companies_buy_app_count=companies_buy_app_count,
        )


class RecyclingCode(BaseNameDescModel):
    gost_name = models.CharField(
        "ГОСТ 24888-81", max_length=10, db_index=True, null=True, unique=True
    )

    class Meta:
        verbose_name = "Код переработки"
        verbose_name_plural = "Коды переработки"
        db_table = "recycling_codes"


class Recyclables(BaseNameDescModel):
    category = models.ForeignKey(
        "product.RecyclablesCategory",
        verbose_name="Категория",
        on_delete=models.CASCADE,
        related_name="recyclables",
    )
    # TODO: Add later
    # recycling_code = models.ForeignKey(
    #     "product.RecyclingCode",
    #     verbose_name="Код переработки",
    #     on_delete=models.CASCADE,
    #     null=True,
    #     related_name="recyclables",
    # )
    objects = RecyclablesQuerySet.as_manager()

    class Meta:
        verbose_name = "Вторсырье"
        verbose_name_plural = "Вторсырье"
        db_table = "recyclables"


class Equipment(BaseNameDescModel):

    category = models.ForeignKey(
        "product.EquipmentCategory",
        verbose_name="Категория",
        on_delete=models.CASCADE,
        related_name="equipments",
    )

    class Meta:
        verbose_name = "Оборудование"
        verbose_name_plural = "Оборудование"
        db_table = "equipments"
