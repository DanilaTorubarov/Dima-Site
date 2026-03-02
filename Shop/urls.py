from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from . import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("django.contrib.auth.urls")),
    path("", views.product_list, name="product_list"),
    path("products/<int:pk>/", views.product_detail, name="product_detail"),
    path("cart/", views.cart_detail, name="cart_detail"),
    path("cart/add/<int:pk>/", views.add_to_cart, name="add_to_cart"),
    path(
        "cart/item/<int:item_id>/update/",
        views.update_cart_item,
        name="update_cart_item",
    ),
    path("cart/share/", views.share_cart, name="share_cart"),
    path("cart/shared/<uuid:pk>/", views.shared_cart_detail, name="shared_cart_detail"),
    path("account/", views.account_dashboard, name="account_dashboard"),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

