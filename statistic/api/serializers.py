from common.serializers import NonNullDynamicFieldsModelSerializer
from exchange.api.serializers import ExchangeRecyclablesSerializer
from exchange.models import RecyclablesDeal, DealStatus, RecyclablesApplication, ApplicationStatus
from product.models import Recyclables
from rest_framework import serializers
from django.db.models import Q


class RecyclablesStatisticsSerializer(ExchangeRecyclablesSerializer):
    def get_deviation_percent(self, instance: Recyclables):
        lower_date_bound = self.context.get("lower_date_bound")
        additional_filters = {}

        if lower_date_bound:
            additional_filters[
                "application__created_at__gte"
            ] = lower_date_bound

        # FIXME: Попробовать сделать через аннотации в get_queryset
        try:
            latest_deal = RecyclablesDeal.objects.filter(
                application__recyclables=instance,
                status=DealStatus.COMPLETED,
                **additional_filters,
            ).latest("created_at")
        except RecyclablesDeal.DoesNotExist:
            latest_deal = None

        if not latest_deal:
            return None

        try:
            first_deal = (
                RecyclablesDeal.objects.filter(
                    application__recyclables=instance,
                    status=DealStatus.COMPLETED,
                    **additional_filters,
                )
                .exclude(pk=latest_deal.pk)
                .earliest("created_at")
            )
        except RecyclablesDeal.DoesNotExist:
            first_deal = None

        if not first_deal:
            return None

        latest_deal_price = float(latest_deal.price)
        pre_latest_deal_price = float(first_deal.price)
        return round(
            (latest_deal_price - pre_latest_deal_price)
            / pre_latest_deal_price
            * 100,
            2,
        )

    def get_deviation(self, instance: Recyclables):
        deviation_percent = self.get_deviation_percent(instance)
        if not deviation_percent or deviation_percent == 0:
            return 0
        if deviation_percent > 0:
            return 1
        return -1


class ShortRecyclablesAppStatisticsSerializer(NonNullDynamicFieldsModelSerializer):

    class Meta:
        model = Recyclables
        fields = ("id", "category", "name")


# ДОБАВИЛ СЕРИАЛАЙЗЕР ДЛЯ recyclables_applications_price
class RecyclablesAppStatisticsSerializer(NonNullDynamicFieldsModelSerializer):
    application_recyclable_status = serializers.IntegerField(read_only=True)
    sales_applications_count = serializers.IntegerField(read_only=True)
    purchase_applications_count = serializers.IntegerField(read_only=True)
    published_date = serializers.DateTimeField(read_only=True)
    lot_size = serializers.FloatField(read_only=True)
    latest_deal_price = serializers.SerializerMethodField(read_only=True)
    deviation_percent = serializers.SerializerMethodField(read_only=True)
    deviation = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Recyclables

    def get_latest_deal_price(self, instance: Recyclables):
        try:
            latest_app = RecyclablesApplication.objects.filter(
                recyclables_id=instance.id,
                status__gte=ApplicationStatus.ON_REVIEW).latest("created_at")
        except RecyclablesApplication.DoesNotExist:
            latest_app = None
        return latest_app.price if latest_app else None

    def get_deviation_percent(self, instance: Recyclables):
        lower_date_bound = self.context.get("lower_date_bound")
        deal_type = self.context.get("deal_type")
        additional_filters = {}

        # ДОБАВИЛ ДЛЯ РАЗДЕЛЕНИЯ ПОКУПКА/ПРОДАЖА
        if deal_type:
            additional_filters[
                "deal_type"
            ] = deal_type

        if lower_date_bound:
            additional_filters[
                "created_at__gte"
            ] = lower_date_bound

        # FIXME: Попробовать сделать через аннотации в get_queryset
        try:
            latest_app = RecyclablesApplication.objects.filter(
                recyclables_id=instance.id,
                status__gte=ApplicationStatus.ON_REVIEW,
                **additional_filters,
            ).latest("created_at")
        except RecyclablesApplication.DoesNotExist:
            latest_app = None
        if not latest_app:
            return None

        try:
            p = (RecyclablesApplication.objects.filter(
                recyclables_id=instance.id,
                status__gte=ApplicationStatus.ON_REVIEW,
                **additional_filters,
            )
                 .exclude(pk=latest_app.pk)
                 )
            first_app = p.order_by('created_at')
        except RecyclablesApplication.DoesNotExist:
            first_app = None

        if not first_app:
            return None

        latest_deal_price = float(latest_app.price)
        pre_latest_deal_price = float(first_app[0].price)
        return round(
            (latest_deal_price - pre_latest_deal_price)
            / pre_latest_deal_price
            * 100,
            2,
        )

    def get_deviation(self, instance: Recyclables):
        deviation_percent = self.get_deviation_percent(instance)
        if not deviation_percent or deviation_percent == 0:
            return 0
        if deviation_percent > 0:
            return 1
        return -1


# ДОБАВИЛ СЕРИАЛАЙЗЕР ДЛЯ main_page_recyclable
class MainPageRecyclableSerializer(NonNullDynamicFieldsModelSerializer):
    application_recyclable_status = serializers.IntegerField(read_only=True)
    sales_applications_count = serializers.IntegerField(read_only=True)
    purchase_applications_count = serializers.IntegerField(read_only=True)
    published_date = serializers.DateTimeField(read_only=True)
    lot_size = serializers.FloatField(read_only=True)
    latest_deal_price = serializers.SerializerMethodField(read_only=True)
    deviation_percent = serializers.SerializerMethodField(read_only=True)
    deviation = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Recyclables

    def get_latest_deal_price(self, instance: Recyclables):
        try:
            latest_app = RecyclablesApplication.objects.filter(
                recyclables_id=instance.id,
                status__gte=ApplicationStatus.ON_REVIEW).latest("created_at")
        except RecyclablesApplication.DoesNotExist:
            latest_app = None
        return latest_app.price if latest_app else None

    def get_deviation_percent(self, instance: Recyclables):
        lower_date_bound = self.context.get("lower_date_bound")
        additional_filters = {}
        if lower_date_bound:
            additional_filters[
                "created_at__gte"
            ] = lower_date_bound

        # FIXME: Попробовать сделать через аннотации в get_queryset
        try:
            latest_app = RecyclablesApplication.objects.filter(
                recyclables_id=instance.id,
                status__gte=ApplicationStatus.ON_REVIEW,
                **additional_filters,
            ).latest("created_at")
        except RecyclablesApplication.DoesNotExist:
            latest_app = None
        if not latest_app:
            return None

        try:
            p = (RecyclablesApplication.objects.filter(
                recyclables_id=instance.id,
                status__gte=ApplicationStatus.ON_REVIEW,
                **additional_filters,
            )
                 .exclude(pk=latest_app.pk)
                 )
            first_app = p.order_by('created_at')
        except RecyclablesApplication.DoesNotExist:
            first_app = None

        if not first_app:
            return None

        latest_deal_price = float(latest_app.price)
        pre_latest_deal_price = float(first_app[0].price)
        return round(
            (latest_deal_price - pre_latest_deal_price)
            / pre_latest_deal_price
            * 100,
            2,
        )

    def get_deviation(self, instance: Recyclables):
        deviation_percent = self.get_deviation_percent(instance)
        if not deviation_percent or deviation_percent == 0:
            return 0
        if deviation_percent > 0:
            return 1
        return -1


class RecyclablesApplicationStatisticsSerializer(
    NonNullDynamicFieldsModelSerializer
):
    recyclables = ExchangeRecyclablesSerializer

    class Meta:
        model = RecyclablesApplication
