from django.core.management.base import BaseCommand
from Shop.models import Category, Product

SERVICES = [
    ("Установка отдельно стоящей ванны",                                        "SERVICE-001",  15000),
    ("Установка наружного смесителя для раковины",                              "SERVICE-002",   8000),
    ("Установка внутреннего смесителя для раковины",                            "SERVICE-003",  12000),
    ("Установка наружного смесителя для ванны",                                 "SERVICE-004",  13000),
    ("Установка внутреннего смесителя для ванны",                               "SERVICE-005",  15000),
    ("Установка внутренней душевой системы",                                    "SERVICE-006",  20000),
    ("Установка наружной душевой системы",                                      "SERVICE-007",  12000),
    ("Установка наружного гигиенического душа",                                 "SERVICE-008",   8000),
    ("Установка внутреннего гигиенического душа",                               "SERVICE-009",  15000),
    ("Установка подвесного унитаза",                                            "SERVICE-010",  12000),
    ("Установка электрического полотенцесушителя (наружное подключение)",       "SERVICE-011A", 10000),
    ("Установка электрического полотенцесушителя (внутреннее подключение)",     "SERVICE-011B", 14000),
    ("Установка тумбы с раковиной",                                             "SERVICE-012",  15000),
    ("Установка кухонного смесителя",                                           "SERVICE-013",  10000),
    ("Установка зеркала с полкой на стену",                                     "SERVICE-014",  10000),
    ("Установка акриловой ванны",                                               "SERVICE-015",  20000),
    ("Установка смесителя для биде",                                            "SERVICE-016",  10000),
    ("Установка гофры 6\"",                                                     "SERVICE-017",   None),
]


class Command(BaseCommand):
    help = "Create the «Услуги монтажа» category and all service products (idempotent)."

    def handle(self, *args, **options):
        category, created = Category.objects.get_or_create(
            slug="montazh",
            defaults={"name": "Услуги монтажа"},
        )
        if created:
            self.stdout.write(self.style.SUCCESS("Created category «Услуги монтажа» (slug: montazh)"))
        else:
            self.stdout.write("Category «Услуги монтажа» already exists — skipping.")

        created_count = 0
        for name, sku, price in SERVICES:
            _, was_created = Product.objects.get_or_create(
                sku=sku,
                defaults={
                    "name": name,
                    "price": price,
                    "category": category,
                    "available": True,
                },
            )
            if was_created:
                created_count += 1
                self.stdout.write(f"  + {name}")

        self.stdout.write(self.style.SUCCESS(
            f"\nDone. {created_count} new service(s) created, "
            f"{len(SERVICES) - created_count} already existed."
        ))
