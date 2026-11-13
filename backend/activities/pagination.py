from rest_framework.pagination import LimitOffsetPagination


class ActivityPagination(LimitOffsetPagination):
    default_limit = 50
    max_limit = 200
