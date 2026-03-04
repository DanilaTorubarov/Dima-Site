from django.contrib import admin

from .models import (
    Cart,
    CartItem,
    Category,
    CategoryCharacteristic,
    Product,
    ProductCharacteristic,
    SharedCart,
    SharedCartItem,
)


class CategoryCharacteristicInline(admin.TabularInline):
    model = CategoryCharacteristic
    extra = 1
    fields = ("name", "char_type", "order")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "parent")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name",)
    inlines = [CategoryCharacteristicInline]


class ProductCharacteristicInline(admin.TabularInline):
    model = ProductCharacteristic
    extra = 0
    fields = ("characteristic", "value")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "characteristic":
            product = getattr(request, "_product_obj", None)
            if product and product.pk:
                kwargs["queryset"] = CategoryCharacteristic.objects.filter(
                    category_id=product.category_id
                )
            else:
                kwargs["queryset"] = CategoryCharacteristic.objects.none()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "category", "available")
    list_filter = ("available", "category")
    search_fields = ("name", "sku")
    inlines = [ProductCharacteristicInline]

    def get_inline_instances(self, request, obj=None):
        request._product_obj = obj
        return super().get_inline_instances(request, obj)


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at", "updated_at")
    inlines = [CartItemInline]


class SharedCartItemInline(admin.TabularInline):
    model = SharedCartItem
    extra = 0


@admin.register(SharedCart)
class SharedCartAdmin(admin.ModelAdmin):
    list_display = ("id", "owner", "created_at")
    inlines = [SharedCartItemInline]
