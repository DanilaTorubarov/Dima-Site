import re

from django import template
from django.utils.html import conditional_escape, mark_safe

register = template.Library()


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
