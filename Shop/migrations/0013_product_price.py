from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Shop', '0012_category_image_category_show_on_homepage'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='price',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Цена (₽)'),
        ),
    ]
