from django.conf import settings
from django.db import models
from django.utils.text import slugify
import uuid


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        related_name="children",
        on_delete=models.CASCADE,
    )
    show_on_homepage = models.BooleanField(
        default=False,
        verbose_name="Показывать на главной",
    )
    image = models.ImageField(
        upload_to="category_images/",
        blank=True,
        null=True,
        verbose_name="Изображение (фон на главной)",
    )

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.name


class Product(models.Model):
    name = models.CharField(max_length=200)
    sku = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="product_images/", blank=True, null=True)
    category = models.ForeignKey(
        Category, related_name="products", on_delete=models.PROTECT
    )
    available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["sku"]),
            models.Index(fields=["name"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.sku})"


class Cart(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        related_name="cart",
        on_delete=models.CASCADE,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Cart for {self.user}"

    @property
    def total_items(self) -> int:
        return sum(item.quantity for item in self.items.all())



class CartItem(models.Model):
    cart = models.ForeignKey(
        Cart, related_name="items", on_delete=models.CASCADE
    )
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = ("cart", "product")

    def __str__(self) -> str:
        return f"{self.quantity} x {self.product}"



class CategoryCharacteristic(models.Model):
    TYPE_TEXT = "text"
    TYPE_NUMERIC = "numeric"
    TYPE_CHOICES = [
        (TYPE_TEXT, "Текст"),
        (TYPE_NUMERIC, "Число"),
    ]

    category = models.ForeignKey(
        Category, related_name="characteristics", on_delete=models.CASCADE
    )
    name = models.CharField(max_length=100)
    char_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default=TYPE_TEXT)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]
        unique_together = ("category", "name")
        verbose_name = "Характеристика категории"
        verbose_name_plural = "Характеристики категорий"

    def __str__(self) -> str:
        return f"{self.category.name} — {self.name}"


class ProductCharacteristic(models.Model):
    product = models.ForeignKey(
        Product, related_name="characteristics", on_delete=models.CASCADE
    )
    characteristic = models.ForeignKey(
        CategoryCharacteristic, related_name="values", on_delete=models.CASCADE
    )
    value = models.CharField(max_length=500)

    class Meta:
        ordering = ["characteristic__order", "characteristic__name"]
        verbose_name = "Характеристика товара"
        verbose_name_plural = "Характеристики товара"

    def __str__(self) -> str:
        return f"{self.product.name}: {self.characteristic.name} = {self.value}"


class SharedCart(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="shared_carts",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Shared cart {self.id}"


class SharedCartItem(models.Model):
    shared_cart = models.ForeignKey(
        SharedCart, related_name="items", on_delete=models.CASCADE
    )
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    def __str__(self) -> str:
        return f"{self.quantity} × {self.product}"


class GuestCart(models.Model):
    """Stores guest (unauthenticated) cart data keyed by IP address."""
    ip_address = models.GenericIPAddressField(unique=True)
    cart_data = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Корзина гостя"
        verbose_name_plural = "Корзины гостей"

    def __str__(self) -> str:
        return f"Guest cart {self.ip_address}"


