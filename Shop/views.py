from difflib import get_close_matches

from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from .forms import RegistrationForm

from .models import Cart, CartItem, Category, CategoryCharacteristic, Product, ProductCharacteristic, SharedCart, SharedCartItem


def _get_or_create_cart_for_user(user):
    cart, _ = Cart.objects.get_or_create(user=user)
    return cart


def _get_cart_quantities(request):
    """Return {product_id: quantity} for the current user/session cart."""
    if request.user.is_authenticated:
        try:
            return {item.product_id: item.quantity for item in request.user.cart.items.all()}
        except Exception:
            return {}
    result = {}
    for k, v in request.session.get("cart", {}).items():
        try:
            result[int(k)] = int(v)
        except (ValueError, TypeError):
            pass
    return result


def _get_category_ancestors(category):
    chain = []
    current = category
    while current is not None:
        chain.append(current)
        current = current.parent
    return list(reversed(chain))


def _get_category_descendant_ids(root):
    ids = [root.id]
    frontier = [root]
    while frontier:
        children = list(Category.objects.filter(parent__in=frontier))
        if not children:
            break
        ids.extend(c.id for c in children)
        frontier = children
    return ids


def _build_char_filters(request, current_category, base_products):
    """
    Return a list of filter dicts for the sidebar and apply them to the product queryset.
    Each dict has: char, type, param_key, and type-specific fields.
    Returns (char_filters, filtered_products).
    """
    if not current_category:
        return [], base_products

    characteristics = CategoryCharacteristic.objects.filter(
        category=current_category
    ).order_by("order", "name")

    products = base_products
    char_filters = []

    for char in characteristics:
        param_key = f"char_{char.id}"

        if char.char_type == CategoryCharacteristic.TYPE_NUMERIC:
            # Compute global min/max from base products (before applying this filter)
            raw_values = list(
                ProductCharacteristic.objects.filter(
                    characteristic=char, product__in=base_products
                ).values_list("value", flat=True)
            )
            float_values = []
            for v in raw_values:
                try:
                    float_values.append(float(v))
                except (ValueError, TypeError):
                    pass

            if not float_values:
                continue

            global_min = min(float_values)
            global_max = max(float_values)
            is_int = all(v == int(v) for v in float_values)

            sel_min_str = request.GET.get(f"{param_key}_min", "").strip()
            sel_max_str = request.GET.get(f"{param_key}_max", "").strip()

            try:
                sel_min = float(sel_min_str) if sel_min_str else global_min
            except ValueError:
                sel_min = global_min
            try:
                sel_max = float(sel_max_str) if sel_max_str else global_max
            except ValueError:
                sel_max = global_max

            # Apply filter only when the user actually sent params
            if sel_min_str or sel_max_str:
                matching_ids = set()
                for pc in ProductCharacteristic.objects.filter(
                    characteristic=char, product__in=products
                ).values_list("product_id", "value"):
                    try:
                        val = float(pc[1])
                        if sel_min <= val <= sel_max:
                            matching_ids.add(pc[0])
                    except (ValueError, TypeError):
                        pass
                products = products.filter(id__in=matching_ids)

            def _fmt(v, is_int=is_int):
                return int(round(v)) if is_int else round(v, 2)

            char_filters.append({
                "char": char,
                "type": "numeric",
                "param_key": param_key,
                "global_min": _fmt(global_min),
                "global_max": _fmt(global_max),
                "selected_min": _fmt(sel_min),
                "selected_max": _fmt(sel_max),
                "is_int": is_int,
                "is_active": sel_min_str != "" or sel_max_str != "",
            })

        else:  # TYPE_TEXT
            all_values = list(
                ProductCharacteristic.objects.filter(
                    characteristic=char, product__in=base_products
                ).values_list("value", flat=True).distinct().order_by("value")
            )

            if not all_values:
                continue

            selected_values = request.GET.getlist(param_key)

            if selected_values:
                matching_ids = list(
                    ProductCharacteristic.objects.filter(
                        characteristic=char,
                        product__in=products,
                        value__in=selected_values,
                    ).values_list("product_id", flat=True)
                )
                products = products.filter(id__in=matching_ids)

            char_filters.append({
                "char": char,
                "type": "text",
                "param_key": param_key,
                "values": all_values,
                "selected_values": selected_values,
                "is_active": bool(selected_values),
            })

    return char_filters, products


PRODUCTS_PER_PAGE = 30


def _smart_search(base_qs, query):
    """
    Return (queryset, suggestions).
    1. Try exact icontains match.
    2. If no results, try every word (OR logic).
    3. If still no results, use difflib for fuzzy name suggestions.
    """
    # Primary: whole-phrase containment
    qs = base_qs.filter(name__icontains=query)
    if qs.exists():
        return qs, []

    # Secondary: any word matches (ignore short stop-words)
    words = [w for w in query.split() if len(w) > 1]
    if words:
        q = Q()
        for w in words:
            q |= Q(name__icontains=w)
        qs = base_qs.filter(q)
        if qs.exists():
            return qs, []

    # Tertiary: fuzzy suggestions from all available product names
    all_names = list(
        Product.objects.filter(available=True).values_list("name", flat=True)
    )
    suggestions = get_close_matches(query, all_names, n=5, cutoff=0.45)
    return base_qs.none(), suggestions


def product_list(request):
    base_products = Product.objects.select_related("category").filter(available=True)
    categories = Category.objects.all()

    search_query = request.GET.get("q", "").strip()
    sku_query = request.GET.get("sku", "").strip()
    category_slug = request.GET.get("category", "").strip()
    search_suggestions = []

    if search_query:
        base_products, search_suggestions = _smart_search(base_products, search_query)

    if sku_query:
        base_products = base_products.filter(sku__icontains=sku_query)

    current_category = None
    category_breadcrumb = []
    category_children = []
    if category_slug:
        current_category = get_object_or_404(Category, slug=category_slug)
        ids = _get_category_descendant_ids(current_category)
        base_products = base_products.filter(category_id__in=ids)
        category_breadcrumb = _get_category_ancestors(current_category)
        category_children = list(current_category.children.order_by("name"))

    char_filters, products = _build_char_filters(request, current_category, base_products)

    has_active_char_filter = any(cf["is_active"] for cf in char_filters)

    paginator = Paginator(products, PRODUCTS_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    context = {
        "products": page_obj,
        "page_obj": page_obj,
        "categories": categories,
        "active_category_slug": category_slug,
        "search_query": search_query,
        "sku_query": sku_query,
        "current_category": current_category,
        "category_breadcrumb": category_breadcrumb,
        "char_filters": char_filters,
        "has_active_char_filter": has_active_char_filter,
        "search_suggestions": search_suggestions,
        "category_children": category_children,
        "cart_quantities": _get_cart_quantities(request),
    }
    return render(request, "main/product_list.html", context)


def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk, available=True)
    category_breadcrumb = []
    if product.category:
        category_breadcrumb = _get_category_ancestors(product.category)

    # Group characteristic values by their CategoryCharacteristic, preserving order
    characteristics = []
    seen = {}
    for pc in product.characteristics.select_related("characteristic").order_by(
        "characteristic__order", "characteristic__name"
    ):
        char = pc.characteristic
        if char.pk not in seen:
            seen[char.pk] = []
            characteristics.append((char, seen[char.pk]))
        seen[char.pk].append(pc.value)

    return render(
        request,
        "main/product_detail.html",
        {
            "product": product,
            "category_breadcrumb": category_breadcrumb,
            "characteristics": characteristics,
            "cart_quantities": _get_cart_quantities(request),
        },
    )

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
    cart = None

    if request.user.is_authenticated:
        cart = _get_or_create_cart_for_user(request.user)
        for item in cart.items.select_related("product"):
            items.append(item)
            total_items += item.quantity
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
                guest_item = type(
                    "GuestCartItem",
                    (),
                    {"product": product, "quantity": quantity},
                )
                items.append(guest_item)
                total_items += quantity

    context = {
        "cart": cart,
        "items": items,
        "total_items": total_items,
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


def register(request):
    if request.user.is_authenticated:
        return redirect("product_list")

    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("product_list")
    else:
        form = RegistrationForm()

    return render(request, "registration/register.html", {"form": form})

@require_POST
def set_cart_quantity(request, pk):
    """Set an exact quantity for a product in the cart (0 = remove). Returns JSON."""
    product = get_object_or_404(Product, pk=pk, available=True)
    try:
        quantity = max(0, int(request.POST.get("quantity", 0)))
    except (ValueError, TypeError):
        quantity = 0

    if request.user.is_authenticated:
        cart = _get_or_create_cart_for_user(request.user)
        if quantity == 0:
            CartItem.objects.filter(cart=cart, product=product).delete()
        else:
            item, created = CartItem.objects.get_or_create(
                cart=cart, product=product, defaults={"quantity": quantity}
            )
            if not created:
                item.quantity = quantity
                item.save()
    else:
        cart = request.session.get("cart", {})
        key = str(product.pk)
        if quantity == 0:
            cart.pop(key, None)
        else:
            cart[key] = quantity
        request.session["cart"] = cart
        request.session.modified = True

    return JsonResponse({"quantity": quantity})


def howtobuy(request):
    return render(request, "main/howtobuy.html")