from datetime import datetime, timedelta, timezone


CART_MAX_AGE = timedelta(weeks=1)


def _get_client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR", "")


class GuestCartMiddleware:
    """
    For unauthenticated users:
    - Expire session carts older than 1 week.
    - Sync the cart with a DB record keyed by IP so all browsers
      from the same IP share one cart.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated:
            self._restore(request)

        response = self.get_response(request)

        if not request.user.is_authenticated:
            self._persist(request)

        return response

    def _restore(self, request):
        from .models import GuestCart

        ip = _get_client_ip(request)
        now = datetime.now(timezone.utc)

        try:
            gc = GuestCart.objects.get(ip_address=ip)
        except GuestCart.DoesNotExist:
            return

        # Expire DB record if older than 1 week
        if now - gc.updated_at > CART_MAX_AGE:
            gc.delete()
            request.session.pop("cart", None)
            return

        # Restore cart into session if session has none
        if not request.session.get("cart"):
            request.session["cart"] = gc.cart_data
            request.session.modified = True

    def _persist(self, request):
        from .models import GuestCart

        ip = _get_client_ip(request)
        cart = request.session.get("cart", {})

        if cart:
            GuestCart.objects.update_or_create(
                ip_address=ip,
                defaults={"cart_data": cart},
            )
        else:
            GuestCart.objects.filter(ip_address=ip).delete()
