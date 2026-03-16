from django.contrib import admin

from .models import (
    Cart,
    CartItem,
    Category,
    CategoryCharacteristic,
    Product,
    ProductCharacteristic,
    ProductImage,
    SharedCart,
    SharedCartItem,
)


class CategoryCharacteristicInline(admin.TabularInline):
    model = CategoryCharacteristic
    extra = 1
    fields = ("name", "char_type", "order")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "parent", "show_on_homepage")
    list_filter = ("show_on_homepage",)
    list_editable = ("show_on_homepage",)
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name",)
    fields = ("name", "slug", "parent", "show_on_homepage", "image")
    inlines = [CategoryCharacteristicInline]


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ("image", "order")


class ProductCharacteristicInline(admin.TabularInline):
    model = ProductCharacteristic
    extra = 0
    fields = ("characteristic", "value")

    def get_formset(self, request, obj=None, **kwargs):
        initial = []
        if obj and obj.pk:
            existing_ids = set(
                obj.characteristics.values_list("characteristic_id", flat=True)
            )
            missing = list(
                CategoryCharacteristic.objects.filter(category=obj.category)
                .exclude(id__in=existing_ids)
                .order_by("order", "name")
            )
            initial = [{"characteristic": char.pk} for char in missing]

        kwargs["extra"] = len(initial)
        FormSet = super().get_formset(request, obj, **kwargs)

        if initial:
            _initial = initial
            _orig_init = FormSet.__init__

            def patched_init(self_fs, *args, **kw):
                # Only inject on GET; on POST let submitted data win
                if not kw.get("data") and "initial" not in kw:
                    kw["initial"] = _initial
                _orig_init(self_fs, *args, **kw)

            FormSet = type(FormSet.__name__, (FormSet,), {"__init__": patched_init})

        return FormSet

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
    list_display = ("name", "sku", "category", "price", "available")
    list_editable = ("price",)
    list_filter = ("available", "category")
    search_fields = ("name", "sku")
    inlines = [ProductImageInline, ProductCharacteristicInline]

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
