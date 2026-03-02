from django.contrib import admin

from .models import Cart, CartItem, Category, Product, SharedCart, SharedCartItem


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "category", "price", "available")
    list_filter = ("available", "category")
    search_fields = ("name", "sku")


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

