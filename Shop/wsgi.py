"""
WSGI config for Shop project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/wsgi/
"""

import os, sys

from django.core.wsgi import get_wsgi_application

sys.path.insert(0, '/var/www/u3438266/data/www/hydro-point.ru')
sys.path.insert(1, '/var/www/u3438266/data/djangoenv/lib/python3.7/site-packages')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Shop.settings')

application = get_wsgi_application()
