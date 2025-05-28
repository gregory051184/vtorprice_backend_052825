import json
import os
from django.db.models import Q
from django.contrib.auth import get_user_model, logout
from django.core.mail import send_mail
from django_filters import FilterSet
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.mixins import UpdateModelMixin, CreateModelMixin
from rest_framework.parsers import FormParser, MultiPartParser, JSONParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.serializers import TokenRefreshSerializer

from requests import post
from company.models import Company
from user.api.serializers import (
    CreateUserSerializer,
    UserSerializer,
    PhoneConfirmSerializer,
    UserObtainTokenSerializer,
    UpdateUserSerializer,
    UpdateUserRoleSerializer,
)
from user.models import UserRole
from user.services.sms_ru import make_phone_call

User = get_user_model()


# АВТОРИЗАЦИЯ ПОЛЬЗОВАТЕЛЯ
class AuthViewSet(CreateModelMixin, viewsets.GenericViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = (AllowAny,)

    def get_serializer_class(self):
        if self.action == "make_call":
            return CreateUserSerializer
        elif self.action == "phone_confirm":
            return PhoneConfirmSerializer
        else:
            return self.serializer_class

    @action(methods=["POST"], detail=False)
    def create_staff_user(self, request, *args, **kwargs):
        # serializer = self.get_serializer(data=request.data)
        if int(request.user.company.owner.id) == int(request.user.id) and int(request.user.company.id) == int(
                request.data["company"]):
            current_company = Company.objects.get(id=int(request.data['company']))
            user = User.objects.create_user(
                phone=request.data['phone'],
                first_name=request.data['first_name'],
                last_name=request.data['last_name'],
                middle_name=request.data['middle_name'],
                position=request.data['position'],
                company_id=request.data['company'],
                role=UserRole.COMPANY_STAFF
                # password=generate_password(10)
            )
            user.save()
            current_company.staff.append(user.id)
            current_company.save()
            # serializer.is_valid(raise_exception=True)
            # self.perform_create(serializer)
            # headers = self.get_success_headers(serializer.data)
            return Response(status=status.HTTP_201_CREATED)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(methods=["GET"], detail=False)
    def company_staff(self, request, *args, **kwargs):
        company_id = request.query_params['id']
        current_company = Company.objects.get(id=company_id)
        if current_company.owner:
            staff = User.objects.filter(~Q(id=current_company.owner.id), company_id=current_company.id)

            serializer = self.get_serializer(staff, many=True)

            return Response(serializer.data, status=status.HTTP_200_OK)
        if current_company.id:
            staff = User.objects.filter(company_id=current_company.id)

            serializer = self.get_serializer(staff, many=True)

            return Response(serializer.data, status=status.HTTP_200_OK)
        else:
            return Response(status=status.HTTP_204_NO_CONTENT)

    @swagger_auto_schema(
        responses={
            status.HTTP_200_OK: TokenRefreshSerializer(),
        },
        request_body=PhoneConfirmSerializer,
    )
    # метод определяет 4-значный код от пользователя, если нет пароля,
    # то делает его паролем и при помощи jwt шифрует
    # url - domain/api/users/3/phone_confirm/
    # возвращает jwt-токен (телефон и пароль в закодированном виде)
    @action(methods=["POST"], detail=False)
    def make_call(self, request, *args, **kwargs):
        data = request.data
        is_created = False

        try:
            user = User.objects.get(phone=data.get("phone"))
        except User.DoesNotExist:
            serializer = self.get_serializer(data=data)
            serializer.is_valid(raise_exception=True)
            user = serializer.save()
            is_created = True

        try:
            if user.is_staff:
                user.code = 8811
            else:
                code = make_phone_call(
                    user.phone.raw_input, request.META.get("REMOTE_ADDR")
                )
                user.code = code
        except Exception as e:
            raise ValidationError(str(e))

        if not user.password:
            user.set_password(user.code)
        user.save()

        setattr(user, "is_created", is_created)
        serializer = self.get_serializer(user)

        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(methods=["POST"], detail=True)
    def phone_confirm(self, request, pk=None, *args, **kwargs):
        user = self.get_object()
        serializer = self.get_serializer(
            data=request.data, context=self.get_serializer_context()
        )
        serializer.is_valid(raise_exception=True)
        # проверяем совпадает ли код, который был передан sms.ru
        # с кодом, который ввёл пользователь
        if (
                user.code == serializer.validated_data["code"]
                or serializer.validated_data["code"]
                == "8811"  # FIXME: remove condition after publication
        ):
            # Создаём jwt-токен для передачи его клиенту
            jwt_serializer = UserObtainTokenSerializer(
                data={"phone": user.phone.as_e164, "password": user.password},
                context={"request": request},
            )
            jwt_serializer.is_valid(raise_exception=True)

            data = jwt_serializer.validated_data
            # Временно добавил для сотрудников компании
            if user.role == UserRole.COMPANY_STAFF:
                data["has_company"] = True

            # TODO: когда появятся сотрудники компаний, необходимо
            #  предусмотреть для них флоу и переписать этот блок
            if user.role == UserRole.COMPANY_ADMIN:
                data["has_company"] = hasattr(user, "my_company")
            return Response(data, status=status.HTTP_200_OK)


        else:
            raise ValidationError("Введен некорректный код")

    @action(["POST"], detail=False)
    def send_offers_by_email(self, request):
        link = request.data.get('link')
        company_id = request.data.get('company')
        companies = request.data.get('companies')
        if company_id:
            company = Company.objects.get(id=company_id)
            send_mail(
                'Предложение от Вторпрайс',
                f'Здравствуйте, перейдите по ссылке {link} для получения актуальных предложений для вашей компании.',
                'vtorprice.mail@yandex.ru',
                [company.email]
            )
            return Response(status=status.HTTP_200_OK)
        if len(companies) > 0:
            for elem in companies:
                if elem["checked"]:
                    company = Company.objects.get(id=elem["id"])
                    for_recyclable_id = elem["link"].split('&')[0] + '&'
                    for_company_id = elem["link"].split('&')[1].split('=')[0] + '=' + f'{elem["id"]}'
                    send_mail(
                        f'Предложение от Вторпрайс для компании {company.name}',
                        f'Здравствуйте, перейдите по ссылке {for_recyclable_id + for_company_id} для получения актуальных предложений для вашей компании.',
                        'vtorprice.mail@yandex.ru',
                        [company.email]
                    )
                    return Response(status=status.HTTP_200_OK)

        return Response(status=status.HTTP_503_SERVICE_UNAVAILABLE)

    @action(["POST"], detail=False)
    def send_offers_by_whatsapp(self, request):
        whatsapp_url = 'https://whatsgate.ru/api/v1/send'
        whatsapp_api_key = 'ErLuLaoIRgODGlkATy3CNzLqpou8gRIn'
        whatsapp_id = '67506a033c2f8'
        # Для того чтобы корректно отражалась ссылка она должна быть с протоколом https
        link = request.data.get('link')
        company_id = request.data.get('company')
        companies = request.data.get('companies')
        if company_id:
            company = Company.objects.get(id=company_id)
            data = {
                "WhatsappID": whatsapp_id,  # "67506a033c2f8",
                "async": False,
                "recipient": {
                    "number": company.phone  # "79021817834"
                },
                "message": {
                    "body": f'Предложение от Вторпрайс' +
                            f'Здравствуйте, перейдите по ссылке {link} для получения актуальных предложений для вашей компании.'
                }
            }
            headers = {
                "X-API-Key": whatsapp_api_key,
                'Content-Type': 'application/json'
            }
            post(whatsapp_url, json.dumps(data), headers=headers)
            return Response(status=status.HTTP_200_OK)
        if len(companies) > 0:
            for elem in companies:
                if elem["checked"]:
                    print(elem)
                    company = Company.objects.get(id=elem["id"])
                    for_recyclable_id = elem["link"].split('&')[0] + '&'
                    for_company_id = elem["link"].split('&')[1].split('=')[0] + '=' + f'{elem["id"]}'
                    data = {
                        "WhatsappID": whatsapp_id,  # "67506a033c2f8",
                        "async": False,
                        "recipient": {
                            "number": str(company.phone)  # "79021817834"
                        },
                        "message": {
                            "body": f'Предложение от Вторпрайс для компании {company.name} ' +
                                    f'Здравствуйте, перейдите по ссылке {for_recyclable_id + for_company_id} для получения актуальных предложений для вашей компании.'

                        }
                    }
                    headers = {
                        'X-API-Key': whatsapp_api_key,
                        'Content-Type': 'application/json'

                    }
                    post(whatsapp_url, json.dumps(data), headers=headers)
                    return Response(status=status.HTTP_200_OK)

        return Response(status=status.HTTP_503_SERVICE_UNAVAILABLE)

    @action(["POST"], detail=False)
    def send_offers_by_telegram(self, request):
        telegram_url = 'https://wappi.pro/tapi/sync/message/send'
        telegram_token = '829057d4cfa5725744320ef68101d722af0adb0e'
        profile_id = 'd5d94664-d392'
        link = request.data.get('link')
        company_id = request.data.get('company')
        companies = request.data.get('companies')
        if company_id:
            company = Company.objects.get(id=company_id)
            data = {
                "body": f'Предложение от Вторпрайс' +
                        f'Здравствуйте, перейдите по ссылке {link} для получения актуальных предложений для вашей компании.',
                "recipient": str(company.phone)

            }
            params = {"profile_id": profile_id}
            headers = {
                "Authorization": telegram_token,
                'Content-Type': 'application/json'
            }
            post(telegram_url, json.dumps(data), headers=headers, params=params)
            return Response(status=status.HTTP_200_OK)
        if len(companies) > 0:
            for elem in companies:
                if elem["checked"]:
                    company = Company.objects.get(id=elem["id"])
                    for_recyclable_id = elem["link"].split('&')[0] + '&'
                    for_company_id = elem["link"].split('&')[1].split('=')[0] + '=' + f'{elem["id"]}'
                    data = {
                        "body": f'Предложение от Вторпрайс для компании {company.name} ' +
                                f'Здравствуйте, перейдите по ссылке {for_recyclable_id + for_company_id} для получения актуальных предложений для вашей компании.',
                        "recipient": str(company.phone)

                    }
                    params = {"profile_id": profile_id}
                    headers = {
                        "Authorization": telegram_token,
                        'Content-Type': 'application/json'
                    }
                    post(telegram_url, json.dumps(data), headers=headers, params=params)
                    return Response(status=status.HTTP_200_OK)

        return Response(status=status.HTTP_503_SERVICE_UNAVAILABLE)


class UserFilterSet(FilterSet):
    pass


class UserView(CreateModelMixin, UpdateModelMixin, APIView):
    permission_classes = (IsAuthenticated,)
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_serializer_context(self):
        """
        Extra context provided to the serializer class.
        """
        return {
            "request": self.request,
            "format": self.format_kwarg,
            "view": self,
        }

    def get_serializer(self, *args, **kwargs):
        """
        Return the serializer instance that should be used for validating and
        deserializing input, and for serializing output.
        """
        serializer_class = UpdateUserSerializer
        kwargs.setdefault("context", self.get_serializer_context())
        return serializer_class(*args, **kwargs)

    def get_object(self):
        return getattr(self.request, "user")

    def get(self, request):
        user = self.request.user
        serializer = UserSerializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        responses={
            status.HTTP_200_OK: UserSerializer(),
        },
        request_body=UpdateUserSerializer,
    )
    @action(methods=["PUT"], detail=False)
    def put(self, request, *args, **kwargs):
        user = self.get_object()
        if request.data.get('image') is not None:
            if user.image != '':
                os.remove(os.getcwd() + '/media/' + str(user.image))
        # Удалить
        kwargs = {
            'partial': 3
        }
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)
        # _________________________________________

        # return self.update(request, *args, **kwargs)

    @swagger_auto_schema(
        responses={
            status.HTTP_200_OK: UserSerializer(),
        },
        request_body=UpdateUserSerializer,
    )
    @action(methods=["PATCH"], detail=False)
    def patch(self, request, *args, **kwargs):
        return self.partial_update(request, *args, **kwargs)

    @action(methods=["DELETE"], detail=False)
    def delete(self, request, *args, **kwargs):
        user = self.get_object()
        logout(request)
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
def get(request, pk=None):
    filter_kwargs = {"pk": pk}
    obj = get_object_or_404(User.objects.all(), **filter_kwargs)
    serializer = UserSerializer(obj)
    return Response(serializer.data)


@swagger_auto_schema(methods=["PATCH"], request_body=UpdateUserRoleSerializer)
@api_view(["PATCH"])
def update_user_role(request, pk=None):
    filter_kwargs = {"pk": pk}
    obj = get_object_or_404(User.objects.all(), **filter_kwargs)
    serializer = UpdateUserRoleSerializer(
        data=request.data, instance=obj, context={"request": request}
    )
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)
