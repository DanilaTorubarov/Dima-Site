from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("Shop", "0010_guest_cart"),
    ]

    operations = [
        migrations.AddField(
            model_name="category",
            name="show_on_homepage",
            field=models.BooleanField(default=False, verbose_name="Показывать на главной"),
        ),
        migrations.AddField(
            model_name="category",
            name="image",
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to="category_images/",
                verbose_name="Изображение (фон на главной)",
            ),
        ),
    ]
