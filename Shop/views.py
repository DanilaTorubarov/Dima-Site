from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .models import Cart, CartItem, Category, Product, SharedCart, SharedCartItem


def _get_or_create_cart_for_user(user):
    cart, _ = Cart.objects.get_or_create(user=user)
    return cart


def product_list(request):
    products = Product.objects.select_related("category").filter(available=True)
    categories = Category.objects.all()

    search_query = request.GET.get("q", "").strip()
    sku_query = request.GET.get("sku", "").strip()
    category_slug = request.GET.get("category", "").strip()

    if search_query:
        products = products.filter(name__icontains=search_query)

    if sku_query:
        products = products.filter(sku__iexact=sku_query)

    if category_slug:
        products = products.filter(category__slug=category_slug)

    context = {
        "products": products,
        "categories": categories,
        "active_category_slug": category_slug,
        "search_query": search_query,
        "sku_query": sku_query,
    }
    return render(request, "main/product_list.html", context)


def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk, available=True)
    return render(request, "main/product_detail.html", {"product": product})

def _add_to_session_cart(request, product_id, quantity):
    cart = request.session.get("cart", {})
    key = str(product_id)
    cart[key] = cart.get(key, 0) + quantity
    request.session["cart"] = cart
    request.session.modified = True

@require_POST
def add_to_cart(request, pk):
    product = get_object_or_404(Product, pk=pk, available=True)
    quantity_str = request.POST.get("quantity", "1")
    try:
        quantity = int(quantity_str)
    except ValueError:
        quantity = 1
    if quantity < 1:
        quantity = 1

    if not request.user.is_authenticated:
        _add_to_session_cart(request, product.id, quantity)
        # For guests, stay on the same page they came from
        return redirect(request.META.get("HTTP_REFERER") or "product_list")

    # existing logged‑in logic
    cart = _get_or_create_cart_for_user(request.user)
    item, created = CartItem.objects.get_or_create(
        cart=cart, product=product, defaults={"quantity": quantity}
    )
    if not created:
        item.quantity += quantity
        item.save()

    return redirect(request.META.get("HTTP_REFERER") or "cart_detail")


def cart_detail(request):
    items = []
    total_items = 0
    total_price = Decimal("0.00")
    cart = None

    if request.user.is_authenticated:
        cart = _get_or_create_cart_for_user(request.user)
        for item in cart.items.select_related("product"):
            items.append(item)
            total_items += item.quantity
            total_price += item.product.price * item.quantity
    else:
        session_cart = request.session.get("cart", {})
        if session_cart:
            product_ids = []
            for key in session_cart.keys():
                try:
                    product_ids.append(int(key))
                except ValueError:
                    continue
            products = {
                p.id: p
                for p in Product.objects.filter(
                    id__in=product_ids, available=True
                )
            }
            for product_id_str, qty in session_cart.items():
                try:
                    product_id = int(product_id_str)
                    quantity = int(qty)
                except (ValueError, TypeError):
                    continue
                if quantity <= 0:
                    continue
                product = products.get(product_id)
                if not product:
                    continue
                line_total = product.price * quantity
                guest_item = type(
                    "GuestCartItem",
                    (),
                    {
                        "product": product,
                        "quantity": quantity,
                        "line_total": line_total,
                    },
                )
                items.append(guest_item)
                total_items += quantity
                total_price += line_total

    context = {
        "cart": cart,
        "items": items,
        "total_items": total_items,
        "total_price": total_price,
    }
    return render(request, "main/cart_detail.html", context)


@require_POST
def share_cart(request):
    """
    Create a shareable snapshot of the current cart (guest or logged-in)
    and redirect to a public URL that can be shared with others.
    """
    # Collect items from user cart or session cart
    products_with_qty = {}

    if request.user.is_authenticated:
        cart = _get_or_create_cart_for_user(request.user)
        for item in cart.items.select_related("product"):
            products_with_qty[item.product] = products_with_qty.get(item.product, 0) + item.quantity
        owner = request.user
    else:
        session_cart = request.session.get("cart", {})
        owner = None
        for product_id_str, qty in session_cart.items():
            try:
                product_id = int(product_id_str)
            except ValueError:
                continue
            product = Product.objects.filter(pk=product_id, available=True).first()
            if not product:
                continue
            products_with_qty[product] = products_with_qty.get(product, 0) + int(qty or 0)

    if not products_with_qty:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"error": "empty"}, status=400)
        return redirect("cart_detail")

    shared_cart = SharedCart.objects.create(owner=owner)
    for product, quantity in products_with_qty.items():
        if quantity > 0:
            SharedCartItem.objects.create(
                shared_cart=shared_cart,
                product=product,
                quantity=quantity,
            )

    shared_url = request.build_absolute_uri(
        reverse("shared_cart_detail", args=[shared_cart.id])
    )
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"url": shared_url})
    return redirect(shared_url)


def shared_cart_detail(request, pk):
    shared_cart = get_object_or_404(SharedCart.objects.prefetch_related("items__product"), pk=pk)
    items = shared_cart.items.all()
    return render(
        request,
        "main/shared_cart_detail.html",
        {
            "shared_cart": shared_cart,
            "items": items,
        },
    )


@login_required
@require_POST
def update_cart_item(request, item_id):
    cart = _get_or_create_cart_for_user(request.user)
    item = get_object_or_404(CartItem, id=item_id, cart=cart)

    action = request.POST.get("action")
    quantity_str = request.POST.get("quantity", "").strip()

    if action == "remove":
        item.delete()
    else:
        try:
            quantity = int(quantity_str)
        except ValueError:
            quantity = item.quantity
        if quantity < 1:
            item.delete()
        else:
            item.quantity = quantity
            item.save()

    return redirect("cart_detail")


@login_required
def account_dashboard(request):
    cart = None
    items = []
    if hasattr(request.user, "cart"):
        cart = request.user.cart
        items = cart.items.select_related("product")

    context = {
        "cart": cart,
        "items": items,
    }
    return render(request, "main/account_dashboard.html", context)

