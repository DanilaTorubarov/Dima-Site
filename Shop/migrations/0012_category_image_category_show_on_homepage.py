from django.db import migrations, models


class Migration(migrations.Migration):
    """
    The category.image and category.show_on_homepage columns already exist in
    the database (added outside of migrations). Use SeparateDatabaseAndState so
    Django records the migration as applied without issuing any ALTER TABLE.
    """

    dependencies = [
        ('Shop', '0011_category_image_category_show_on_homepage_and_more'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],  # nothing to do – columns already exist
            state_operations=[
                migrations.AddField(
                    model_name='category',
                    name='image',
                    field=models.ImageField(blank=True, null=True, upload_to='category_images/', verbose_name='Изображение (фон на главной)'),
                ),
                migrations.AddField(
                    model_name='category',
                    name='show_on_homepage',
                    field=models.BooleanField(default=False, verbose_name='Показывать на главной'),
                ),
            ],
        ),
    ]
