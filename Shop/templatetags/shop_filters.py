import re

from django import template
from django.utils.html import conditional_escape, mark_safe

register = template.Library()


@register.filter
def dict_get(d, key):
    """Return d.get(key) — lets templates look up a dict with a dynamic key."""
    return d.get(key)


@register.simple_tag(takes_context=True)
def url_with_page(context, page_num):
    """Return current query string with page replaced."""
    params = context["request"].GET.copy()
    params["page"] = page_num
    return "?" + params.urlencode()


@register.filter
def format_price(value):
    """Format a decimal/int price as '1 234 ₽'. Returns '' if value is None."""
    if value is None:
        return ""
    try:
        amount = int(round(float(value)))
        formatted = f"{amount:,}".replace(",", "\u00a0")  # non-breaking space
        return f"{formatted}\u00a0₽"
    except (TypeError, ValueError):
        return f"{value}\u00a0₽"


@register.filter(needs_autoescape=True)
def render_description(value, autoescape=True):
    """
    Renders product description with basic formatting:
    - **text** → <strong>text</strong>
    - newlines → <br>
    """
    if not value:
        return ""
    esc = conditional_escape if autoescape else lambda x: x
    value = esc(value)
    value = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", value)
    value = value.replace("\n", "<br>")
    return mark_safe(value)
