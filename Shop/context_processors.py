from .models import Category


def catalog_categories(request):
    root_categories = (
        Category.objects.filter(parent__isnull=True).prefetch_related("children")
    )
    homepage_categories = Category.objects.filter(show_on_homepage=True)
    return {
        "catalog_root_categories": root_categories,
        "homepage_categories": homepage_categories,
    }
