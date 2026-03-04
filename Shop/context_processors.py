from .models import Category


def catalog_categories(request):
    root_categories = (
        Category.objects.filter(parent__isnull=True).prefetch_related("children")
    )
    return {"catalog_root_categories": root_categories}
