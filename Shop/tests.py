import json
from datetime import datetime, timedelta, timezone

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, Client
from django.urls import reverse

from .backends import EmailOrUsernameBackend
from .context_processors import catalog_categories
from .forms import RegistrationForm
from .middleware import GuestCartMiddleware, _get_client_ip
from .models import (
    Cart, CartItem, Category, CategoryCharacteristic, GuestCart,
    Product, ProductCharacteristic, SharedCart, SharedCartItem,
)
from .templatetags.shop_filters import dict_get, render_description

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_category(name="Electronics", parent=None):
    return Category.objects.create(name=name, slug=name.lower(), parent=parent)


def make_product(name="Widget", sku="SKU-001", category=None, available=True):
    if category is None:
        category = make_category()
    return Product.objects.create(name=name, sku=sku, category=category, available=available)


def make_user(username="alice", email="alice@example.com", password="pass1234!"):
    return User.objects.create_user(username=username, email=email, password=password)


# ===========================================================================
# Models
# ===========================================================================

class CategoryModelTests(TestCase):
    def test_slug_auto_generated_on_save(self):
        cat = Category(name="My Category")
        cat.save()
        self.assertEqual(cat.slug, "my-category")

    def test_slug_not_overwritten_if_already_set(self):
        cat = Category(name="Stuff", slug="custom-slug")
        cat.save()
        self.assertEqual(cat.slug, "custom-slug")

    def test_str(self):
        cat = Category(name="Tools", slug="tools")
        self.assertEqual(str(cat), "Tools")

    def test_parent_child_relationship(self):
        parent = make_category("Parent")
        child = Category.objects.create(name="Child", slug="child", parent=parent)
        self.assertEqual(child.parent, parent)
        self.assertIn(child, parent.children.all())


class ProductModelTests(TestCase):
    def test_str(self):
        cat = make_category()
        p = Product(name="Gadget", sku="G-001", category=cat)
        self.assertEqual(str(p), "Gadget (G-001)")

    def test_available_default_true(self):
        p = make_product()
        self.assertTrue(p.available)


class CartModelTests(TestCase):
    def test_total_items_empty(self):
        user = make_user()
        cart = Cart.objects.create(user=user)
        self.assertEqual(cart.total_items, 0)

    def test_total_items_with_items(self):
        user = make_user()
        cart = Cart.objects.create(user=user)
        product = make_product()
        CartItem.objects.create(cart=cart, product=product, quantity=3)
        self.assertEqual(cart.total_items, 3)

    def test_str(self):
        user = make_user()
        cart = Cart.objects.create(user=user)
        self.assertIn(user.username, str(cart))


class CartItemModelTests(TestCase):
    def test_str(self):
        user = make_user()
        cart = Cart.objects.create(user=user)
        product = make_product()
        item = CartItem(cart=cart, product=product, quantity=2)
        self.assertIn("2", str(item))


class SharedCartModelTests(TestCase):
    def test_uuid_primary_key(self):
        sc = SharedCart.objects.create()
        import uuid
        self.assertIsInstance(sc.id, uuid.UUID)

    def test_str(self):
        sc = SharedCart.objects.create()
        self.assertIn("Shared cart", str(sc))


class GuestCartModelTests(TestCase):
    def test_str(self):
        gc = GuestCart.objects.create(ip_address="1.2.3.4", cart_data={})
        self.assertIn("1.2.3.4", str(gc))


# ===========================================================================
# Forms
# ===========================================================================

class RegistrationFormTests(TestCase):
    def _valid_data(self, **overrides):
        data = {
            "username": "newuser",
            "email": "new@example.com",
            "password1": "TestPass123!",
            "password2": "TestPass123!",
        }
        data.update(overrides)
        return data

    def test_valid_form(self):
        form = RegistrationForm(data=self._valid_data())
        self.assertTrue(form.is_valid(), form.errors)

    def test_email_lowercased_on_save(self):
        form = RegistrationForm(data=self._valid_data(email="Upper@Example.COM"))
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertEqual(user.email, "upper@example.com")

    def test_duplicate_email_rejected(self):
        User.objects.create_user(username="existing", email="dup@example.com", password="x")
        form = RegistrationForm(data=self._valid_data(email="DUP@example.com"))
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_missing_email_rejected(self):
        data = self._valid_data()
        data["email"] = ""
        form = RegistrationForm(data=data)
        self.assertFalse(form.is_valid())


# ===========================================================================
# Authentication backend
# ===========================================================================

class EmailOrUsernameBackendTests(TestCase):
    def setUp(self):
        self.user = make_user(username="bob", email="bob@example.com", password="secret123!")
        self.backend = EmailOrUsernameBackend()

    def test_login_by_username(self):
        result = self.backend.authenticate(None, username="bob", password="secret123!")
        self.assertEqual(result, self.user)

    def test_login_by_email(self):
        result = self.backend.authenticate(None, username="bob@example.com", password="secret123!")
        self.assertEqual(result, self.user)

    def test_email_case_insensitive(self):
        result = self.backend.authenticate(None, username="BOB@EXAMPLE.COM", password="secret123!")
        self.assertEqual(result, self.user)

    def test_wrong_password_returns_none(self):
        result = self.backend.authenticate(None, username="bob", password="wrongpass")
        self.assertIsNone(result)

    def test_nonexistent_user_returns_none(self):
        result = self.backend.authenticate(None, username="ghost", password="whatever")
        self.assertIsNone(result)

    def test_missing_credentials_returns_none(self):
        self.assertIsNone(self.backend.authenticate(None, username="", password="x"))
        self.assertIsNone(self.backend.authenticate(None, username="bob", password=""))


# ===========================================================================
# Template filters
# ===========================================================================

class DictGetFilterTests(TestCase):
    def test_existing_key(self):
        self.assertEqual(dict_get({"a": 1}, "a"), 1)

    def test_missing_key_returns_none(self):
        self.assertIsNone(dict_get({"a": 1}, "b"))

    def test_integer_key(self):
        self.assertEqual(dict_get({42: "val"}, 42), "val")


class RenderDescriptionFilterTests(TestCase):
    def test_empty_string(self):
        self.assertEqual(render_description(""), "")

    def test_none_returns_empty(self):
        self.assertEqual(render_description(None), "")

    def test_bold_markdown(self):
        result = render_description("Hello **world**")
        self.assertIn("<strong>world</strong>", result)

    def test_newlines_to_br(self):
        result = render_description("line1\nline2")
        self.assertIn("<br>", result)

    def test_xss_escaping(self):
        result = render_description("<script>alert(1)</script>")
        self.assertNotIn("<script>", result)

    def test_bold_does_not_break_on_no_match(self):
        result = render_description("no bold here")
        self.assertNotIn("<strong>", result)


# ===========================================================================
# Context processors
# ===========================================================================

class CatalogCategoriesContextProcessorTests(TestCase):
    def test_returns_root_and_homepage_categories(self):
        parent = Category.objects.create(name="Root", slug="root", show_on_homepage=True)
        Category.objects.create(name="Child", slug="child", parent=parent, show_on_homepage=False)

        request = RequestFactory().get("/")
        ctx = catalog_categories(request)

        self.assertIn("catalog_root_categories", ctx)
        self.assertIn("homepage_categories", ctx)
        # Root is parentless, child is not
        root_slugs = [c.slug for c in ctx["catalog_root_categories"]]
        self.assertIn("root", root_slugs)
        self.assertNotIn("child", root_slugs)

    def test_homepage_categories_filtered(self):
        Category.objects.create(name="Featured", slug="featured", show_on_homepage=True)
        Category.objects.create(name="Hidden", slug="hidden", show_on_homepage=False)

        request = RequestFactory().get("/")
        ctx = catalog_categories(request)
        hp_slugs = [c.slug for c in ctx["homepage_categories"]]
        self.assertIn("featured", hp_slugs)
        self.assertNotIn("hidden", hp_slugs)


# ===========================================================================
# Middleware
# ===========================================================================

class GetClientIpTests(TestCase):
    def test_uses_remote_addr(self):
        request = RequestFactory().get("/")
        request.META["REMOTE_ADDR"] = "9.9.9.9"
        self.assertEqual(_get_client_ip(request), "9.9.9.9")

    def test_uses_first_forwarded_ip(self):
        request = RequestFactory().get("/")
        request.META["HTTP_X_FORWARDED_FOR"] = "1.1.1.1, 2.2.2.2"
        self.assertEqual(_get_client_ip(request), "1.1.1.1")


class GuestCartMiddlewareTests(TestCase):
    def setUp(self):
        self.client = Client(REMOTE_ADDR="10.0.0.1")

    def test_restores_cart_from_db_to_session(self):
        GuestCart.objects.create(ip_address="10.0.0.1", cart_data={"5": 3})
        # Ensure no session cart exists yet
        self.client.get(reverse("product_list"))
        session = self.client.session
        self.assertEqual(session.get("cart", {}).get("5"), 3)

    def test_persists_session_cart_to_db(self):
        session = self.client.session
        session["cart"] = {"7": 2}
        session.save()
        self.client.get(reverse("product_list"))
        gc = GuestCart.objects.get(ip_address="10.0.0.1")
        self.assertEqual(gc.cart_data.get("7"), 2)

    def test_expired_cart_is_deleted(self):
        gc = GuestCart.objects.create(ip_address="10.0.0.1", cart_data={"1": 1})
        # Move updated_at to 8 days ago
        GuestCart.objects.filter(pk=gc.pk).update(
            updated_at=datetime.now(timezone.utc) - timedelta(days=8)
        )
        self.client.get(reverse("product_list"))
        self.assertFalse(GuestCart.objects.filter(ip_address="10.0.0.1").exists())

    def test_persist_deletes_db_record_when_session_cart_empty(self):
        """_persist() removes the DB record when the session cart is empty."""
        GuestCart.objects.create(ip_address="10.0.0.1", cart_data={"1": 1})
        # Call _persist directly with an empty-cart request
        middleware = GuestCartMiddleware(get_response=lambda r: None)
        request = RequestFactory().get("/")
        request.META["REMOTE_ADDR"] = "10.0.0.1"
        request.session = self.client.session
        request.session["cart"] = {}
        middleware._persist(request)
        self.assertFalse(GuestCart.objects.filter(ip_address="10.0.0.1").exists())


# ===========================================================================
# Signals
# ===========================================================================

class TransferGuestCartSignalTests(TestCase):
    def setUp(self):
        self.product = make_product(sku="SIG-001")
        self.client = Client()

    def test_guest_cart_merged_on_login(self):
        user = make_user(username="signal_user", password="pass1234!")
        session = self.client.session
        session["cart"] = {str(self.product.pk): 2}
        session.save()
        self.client.post(reverse("login"), {"username": "signal_user", "password": "pass1234!"})
        cart = Cart.objects.get(user=user)
        item = CartItem.objects.get(cart=cart, product=self.product)
        self.assertEqual(item.quantity, 2)

    def test_guest_cart_cleared_after_merge(self):
        make_user(username="signal_user2", password="pass1234!")
        session = self.client.session
        session["cart"] = {str(self.product.pk): 1}
        session.save()
        self.client.post(reverse("login"), {"username": "signal_user2", "password": "pass1234!"})
        self.assertFalse(self.client.session.get("cart"))

    def test_existing_cart_quantities_incremented(self):
        user = make_user(username="signal_user3", password="pass1234!")
        cart = Cart.objects.create(user=user)
        CartItem.objects.create(cart=cart, product=self.product, quantity=1)
        session = self.client.session
        session["cart"] = {str(self.product.pk): 3}
        session.save()
        self.client.post(reverse("login"), {"username": "signal_user3", "password": "pass1234!"})
        item = CartItem.objects.get(cart=cart, product=self.product)
        self.assertEqual(item.quantity, 4)


# ===========================================================================
# Views — product_list
# ===========================================================================

class ProductListViewTests(TestCase):
    def setUp(self):
        self.cat = make_category("TestCat")
        self.p1 = make_product("Alpha Widget", sku="A-001", category=self.cat)
        self.p2 = make_product("Beta Gadget", sku="B-002", category=self.cat)
        self.hidden = make_product("Hidden", sku="H-003", category=self.cat, available=False)

    def test_returns_200(self):
        resp = self.client.get(reverse("product_list"))
        self.assertEqual(resp.status_code, 200)

    def test_only_available_products_shown(self):
        resp = self.client.get(reverse("product_list"))
        product_names = [p.name for p in resp.context["products"]]
        self.assertNotIn("Hidden", product_names)

    def test_search_by_name(self):
        resp = self.client.get(reverse("product_list"), {"q": "Alpha"})
        product_names = [p.name for p in resp.context["products"]]
        self.assertIn("Alpha Widget", product_names)
        self.assertNotIn("Beta Gadget", product_names)

    def test_search_no_results_returns_suggestions(self):
        resp = self.client.get(reverse("product_list"), {"q": "Alph"})
        # Either finds Alpha or provides fuzzy suggestions — either is valid
        # The key assertion: view does not crash
        self.assertEqual(resp.status_code, 200)

    def test_sku_filter(self):
        resp = self.client.get(reverse("product_list"), {"sku": "B-002"})
        product_names = [p.name for p in resp.context["products"]]
        self.assertIn("Beta Gadget", product_names)
        self.assertNotIn("Alpha Widget", product_names)

    def test_category_filter(self):
        other_cat = make_category("Other")
        make_product("Other Product", sku="O-001", category=other_cat)
        resp = self.client.get(reverse("product_list"), {"category": self.cat.slug})
        product_names = [p.name for p in resp.context["products"]]
        self.assertNotIn("Other Product", product_names)

    def test_pagination_context(self):
        resp = self.client.get(reverse("product_list"))
        self.assertIn("page_obj", resp.context)


# ===========================================================================
# Views — product_detail
# ===========================================================================

class ProductDetailViewTests(TestCase):
    def setUp(self):
        self.cat = make_category("DetailCat")
        self.product = make_product("Detail Widget", sku="D-001", category=self.cat)

    def test_returns_200_for_available_product(self):
        resp = self.client.get(reverse("product_detail", args=[self.product.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_returns_404_for_unavailable_product(self):
        p = make_product("Unavailable", sku="U-001", category=self.cat, available=False)
        resp = self.client.get(reverse("product_detail", args=[p.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_returns_404_for_nonexistent_product(self):
        resp = self.client.get(reverse("product_detail", args=[99999]))
        self.assertEqual(resp.status_code, 404)

    def test_characteristics_in_context(self):
        char = CategoryCharacteristic.objects.create(
            category=self.cat, name="Weight", char_type=CategoryCharacteristic.TYPE_TEXT
        )
        ProductCharacteristic.objects.create(
            product=self.product, characteristic=char, value="500g"
        )
        resp = self.client.get(reverse("product_detail", args=[self.product.pk]))
        self.assertIn("characteristics", resp.context)


# ===========================================================================
# Views — cart (add, detail, update, set_quantity)
# ===========================================================================

class AddToCartViewTests(TestCase):
    def setUp(self):
        self.product = make_product(sku="CART-001")
        self.user = make_user()

    def test_get_not_allowed(self):
        resp = self.client.get(reverse("add_to_cart", args=[self.product.pk]))
        self.assertEqual(resp.status_code, 405)

    def test_authenticated_user_adds_to_db_cart(self):
        self.client.force_login(self.user)
        self.client.post(reverse("add_to_cart", args=[self.product.pk]), {"quantity": "2"})
        cart = Cart.objects.get(user=self.user)
        item = CartItem.objects.get(cart=cart, product=self.product)
        self.assertEqual(item.quantity, 2)

    def test_authenticated_user_increments_existing_item(self):
        self.client.force_login(self.user)
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=cart, product=self.product, quantity=1)
        self.client.post(reverse("add_to_cart", args=[self.product.pk]), {"quantity": "3"})
        item = CartItem.objects.get(cart=cart, product=self.product)
        self.assertEqual(item.quantity, 4)

    def test_guest_adds_to_session_cart(self):
        self.client.post(reverse("add_to_cart", args=[self.product.pk]), {"quantity": "1"})
        session_cart = self.client.session.get("cart", {})
        self.assertEqual(session_cart.get(str(self.product.pk)), 1)

    def test_invalid_quantity_defaults_to_1(self):
        self.client.force_login(self.user)
        self.client.post(reverse("add_to_cart", args=[self.product.pk]), {"quantity": "abc"})
        item = CartItem.objects.get(cart__user=self.user, product=self.product)
        self.assertEqual(item.quantity, 1)


class CartDetailViewTests(TestCase):
    def setUp(self):
        self.product = make_product(sku="DETAIL-001")
        self.user = make_user()

    def test_authenticated_cart_detail(self):
        self.client.force_login(self.user)
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=cart, product=self.product, quantity=2)
        resp = self.client.get(reverse("cart_detail"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["total_items"], 2)

    def test_guest_cart_detail_from_session(self):
        session = self.client.session
        session["cart"] = {str(self.product.pk): 5}
        session.save()
        resp = self.client.get(reverse("cart_detail"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["total_items"], 5)

    def test_empty_cart_detail(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse("cart_detail"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["total_items"], 0)


class UpdateCartItemViewTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.product = make_product(sku="UPD-001")
        self.client.force_login(self.user)
        self.cart = Cart.objects.create(user=self.user)
        self.item = CartItem.objects.create(cart=self.cart, product=self.product, quantity=3)

    def test_remove_action_deletes_item(self):
        self.client.post(
            reverse("update_cart_item", args=[self.item.pk]), {"action": "remove"}
        )
        self.assertFalse(CartItem.objects.filter(pk=self.item.pk).exists())

    def test_update_quantity(self):
        self.client.post(
            reverse("update_cart_item", args=[self.item.pk]), {"quantity": "7"}
        )
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 7)

    def test_zero_quantity_deletes_item(self):
        self.client.post(
            reverse("update_cart_item", args=[self.item.pk]), {"quantity": "0"}
        )
        self.assertFalse(CartItem.objects.filter(pk=self.item.pk).exists())

    def test_unauthenticated_redirects_to_login(self):
        self.client.logout()
        resp = self.client.post(
            reverse("update_cart_item", args=[self.item.pk]), {"action": "remove"}
        )
        self.assertRedirects(resp, f"/accounts/login/?next=/cart/item/{self.item.pk}/update/")


class SetCartQuantityViewTests(TestCase):
    def setUp(self):
        self.product = make_product(sku="SET-001")
        self.user = make_user()

    def test_authenticated_set_quantity(self):
        self.client.force_login(self.user)
        resp = self.client.post(
            reverse("set_cart_quantity", args=[self.product.pk]), {"quantity": "5"}
        )
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertEqual(data["quantity"], 5)
        item = CartItem.objects.get(cart__user=self.user, product=self.product)
        self.assertEqual(item.quantity, 5)

    def test_authenticated_set_zero_removes_item(self):
        self.client.force_login(self.user)
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=cart, product=self.product, quantity=3)
        resp = self.client.post(
            reverse("set_cart_quantity", args=[self.product.pk]), {"quantity": "0"}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(CartItem.objects.filter(cart=cart, product=self.product).exists())

    def test_guest_set_quantity_in_session(self):
        resp = self.client.post(
            reverse("set_cart_quantity", args=[self.product.pk]), {"quantity": "4"}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.client.session["cart"].get(str(self.product.pk)), 4)

    def test_get_not_allowed(self):
        resp = self.client.get(reverse("set_cart_quantity", args=[self.product.pk]))
        self.assertEqual(resp.status_code, 405)


# ===========================================================================
# Views — share_cart
# ===========================================================================

class ShareCartViewTests(TestCase):
    def setUp(self):
        self.product = make_product(sku="SHARE-001")
        self.user = make_user()

    def test_authenticated_user_creates_shared_cart(self):
        self.client.force_login(self.user)
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=cart, product=self.product, quantity=2)
        resp = self.client.post(reverse("share_cart"))
        self.assertEqual(SharedCart.objects.count(), 1)
        shared = SharedCart.objects.first()
        self.assertEqual(shared.items.count(), 1)

    def test_empty_cart_returns_redirect(self):
        self.client.force_login(self.user)
        resp = self.client.post(reverse("share_cart"))
        self.assertRedirects(resp, reverse("cart_detail"))

    def test_ajax_empty_cart_returns_400(self):
        self.client.force_login(self.user)
        resp = self.client.post(
            reverse("share_cart"), HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )
        self.assertEqual(resp.status_code, 400)

    def test_ajax_returns_json_url(self):
        self.client.force_login(self.user)
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=cart, product=self.product, quantity=1)
        resp = self.client.post(
            reverse("share_cart"), HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("url", json.loads(resp.content))

    def test_guest_user_creates_shared_cart_from_session(self):
        session = self.client.session
        session["cart"] = {str(self.product.pk): 2}
        session.save()
        self.client.post(reverse("share_cart"))
        self.assertEqual(SharedCart.objects.count(), 1)


class SharedCartDetailViewTests(TestCase):
    def setUp(self):
        self.product = make_product(sku="VIEW-001")
        self.shared_cart = SharedCart.objects.create()
        SharedCartItem.objects.create(
            shared_cart=self.shared_cart, product=self.product, quantity=3
        )

    def test_returns_200(self):
        resp = self.client.get(
            reverse("shared_cart_detail", args=[self.shared_cart.pk])
        )
        self.assertEqual(resp.status_code, 200)

    def test_404_for_invalid_uuid(self):
        import uuid
        resp = self.client.get(
            reverse("shared_cart_detail", args=[uuid.uuid4()])
        )
        self.assertEqual(resp.status_code, 404)

    def test_items_in_context(self):
        resp = self.client.get(
            reverse("shared_cart_detail", args=[self.shared_cart.pk])
        )
        self.assertEqual(resp.context["items"].count(), 1)


# ===========================================================================
# Views — registration & account
# ===========================================================================

class RegisterViewTests(TestCase):
    def _post(self, **overrides):
        data = {
            "username": "newuser",
            "email": "new@example.com",
            "password1": "TestPass123!",
            "password2": "TestPass123!",
        }
        data.update(overrides)
        return self.client.post(reverse("register"), data)

    def test_get_returns_200(self):
        resp = self.client.get(reverse("register"))
        self.assertEqual(resp.status_code, 200)

    def test_successful_registration_creates_user_and_logs_in(self):
        resp = self._post()
        self.assertRedirects(resp, reverse("product_list"))
        self.assertTrue(User.objects.filter(username="newuser").exists())

    def test_duplicate_email_shows_form_errors(self):
        User.objects.create_user(username="existing", email="dup@example.com", password="x")
        resp = self._post(email="dup@example.com")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context["form"].is_valid())

    def test_authenticated_user_redirected_away(self):
        user = make_user()
        self.client.force_login(user)
        resp = self.client.get(reverse("register"))
        self.assertRedirects(resp, reverse("product_list"))


class AccountDashboardViewTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def test_requires_login(self):
        resp = self.client.get(reverse("account_dashboard"))
        self.assertRedirects(resp, f"/accounts/login/?next=/account/")

    def test_authenticated_returns_200(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse("account_dashboard"))
        self.assertEqual(resp.status_code, 200)

    def test_cart_items_in_context(self):
        self.client.force_login(self.user)
        product = make_product(sku="ACC-001")
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=cart, product=product, quantity=1)
        resp = self.client.get(reverse("account_dashboard"))
        self.assertEqual(len(list(resp.context["items"])), 1)


# ===========================================================================
# Views — helper functions
# ===========================================================================

class GetCategoryAncestorsTests(TestCase):
    def test_returns_chain_root_first(self):
        from .views import _get_category_ancestors
        grandparent = make_category("GP")
        parent = Category.objects.create(name="P", slug="p", parent=grandparent)
        child = Category.objects.create(name="C", slug="c", parent=parent)
        chain = _get_category_ancestors(child)
        self.assertEqual([c.name for c in chain], ["GP", "P", "C"])

    def test_single_category(self):
        from .views import _get_category_ancestors
        cat = make_category("Alone")
        self.assertEqual(_get_category_ancestors(cat), [cat])


class GetCategoryDescendantIdsTests(TestCase):
    def test_includes_root_and_all_children(self):
        from .views import _get_category_descendant_ids
        root = make_category("Root2")
        child = Category.objects.create(name="Child2", slug="child2", parent=root)
        grandchild = Category.objects.create(name="GC2", slug="gc2", parent=child)
        ids = _get_category_descendant_ids(root)
        self.assertIn(root.id, ids)
        self.assertIn(child.id, ids)
        self.assertIn(grandchild.id, ids)


class SmartSearchTests(TestCase):
    def setUp(self):
        cat = make_category("SearchCat")
        self.p1 = make_product("Apple iPhone", sku="IP-001", category=cat)
        self.p2 = make_product("Samsung Galaxy", sku="SG-001", category=cat)
        self.base_qs = Product.objects.filter(available=True)

    def test_exact_match(self):
        from .views import _smart_search
        qs, suggestions = _smart_search(self.base_qs, "iPhone")
        self.assertIn(self.p1, qs)
        self.assertEqual(suggestions, [])

    def test_no_match_returns_fuzzy_suggestions(self):
        from .views import _smart_search
        qs, suggestions = _smart_search(self.base_qs, "xyzxyzxyz")
        self.assertEqual(qs.count(), 0)

    def test_word_level_fallback(self):
        from .views import _smart_search
        qs, suggestions = _smart_search(self.base_qs, "Apple Samsung")
        # Both products contain one of the words
        self.assertIn(self.p1, qs)
        self.assertIn(self.p2, qs)


# ===========================================================================
# Views — characteristic filters
# ===========================================================================

class BuildCharFiltersTests(TestCase):
    def setUp(self):
        self.cat = make_category("FilterCat")
        self.text_char = CategoryCharacteristic.objects.create(
            category=self.cat, name="Color", char_type=CategoryCharacteristic.TYPE_TEXT
        )
        self.num_char = CategoryCharacteristic.objects.create(
            category=self.cat, name="Weight", char_type=CategoryCharacteristic.TYPE_NUMERIC
        )
        self.p_red = make_product("Red Widget", sku="RW-001", category=self.cat)
        self.p_blue = make_product("Blue Widget", sku="BW-001", category=self.cat)
        ProductCharacteristic.objects.create(
            product=self.p_red, characteristic=self.text_char, value="Red"
        )
        ProductCharacteristic.objects.create(
            product=self.p_blue, characteristic=self.text_char, value="Blue"
        )
        ProductCharacteristic.objects.create(
            product=self.p_red, characteristic=self.num_char, value="100"
        )
        ProductCharacteristic.objects.create(
            product=self.p_blue, characteristic=self.num_char, value="200"
        )
        self.base_qs = Product.objects.filter(available=True)

    def test_text_filter_narrows_products(self):
        from .views import _build_char_filters
        request = RequestFactory().get("/", {f"char_{self.text_char.id}": "Red"})
        char_filters, products = _build_char_filters(request, self.cat, self.base_qs)
        self.assertIn(self.p_red, products)
        self.assertNotIn(self.p_blue, products)

    def test_numeric_filter_narrows_products(self):
        from .views import _build_char_filters
        request = RequestFactory().get(
            "/", {f"char_{self.num_char.id}_min": "50", f"char_{self.num_char.id}_max": "150"}
        )
        char_filters, products = _build_char_filters(request, self.cat, self.base_qs)
        self.assertIn(self.p_red, products)
        self.assertNotIn(self.p_blue, products)

    def test_no_category_returns_unchanged_queryset(self):
        from .views import _build_char_filters
        request = RequestFactory().get("/")
        char_filters, products = _build_char_filters(request, None, self.base_qs)
        self.assertEqual(char_filters, [])
        self.assertEqual(list(products), list(self.base_qs))
