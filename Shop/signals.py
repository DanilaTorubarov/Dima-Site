from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from .models import Cart, CartItem, Product

@receiver(user_logged_in)
def transfer_guest_cart(sender, request, user, **kwargs):
    session_cart = request.session.get("cart")
    if not session_cart:
        return

    cart, _ = Cart.objects.get_or_create(user=user)

    for product_id_str, qty in session_cart.items():
        try:
            product_id = int(product_id_str)
        except ValueError:
            continue

        product = Product.objects.filter(pk=product_id, available=True).first()
        if not product:
            continue

        item, created = CartItem.objects.get_or_create(
            cart=cart, product=product, defaults={"quantity": qty}
        )
        if not created:
            item.quantity += qty
            item.save()

    # clear session cart once merged
    if "cart" in request.session:
        del request.session["cart"]
        request.session.modified = True