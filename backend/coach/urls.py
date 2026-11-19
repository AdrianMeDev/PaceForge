from django.urls import path

from . import views

urlpatterns = [
    path("provider/", views.ProviderView.as_view(), name="coach-provider"),
    path("provider/check/", views.ProviderCheckView.as_view(), name="coach-provider-check"),
    path("costs/", views.CostsView.as_view(), name="coach-costs"),
    path("costs/prices/", views.ModelPricesView.as_view(), name="coach-costs-prices"),
    path(
        "costs/prices/<int:price_id>/",
        views.ModelPriceDetailView.as_view(),
        name="coach-costs-price",
    ),
]
