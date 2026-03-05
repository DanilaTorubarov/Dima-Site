# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, '/var/www/u3438266/data/www/hydro-point.ru/Shop')
sys.path.insert(1, '/var/www/u3438266/data/www/hydro-point.ru/venv/lib/python3.10/site-packages')
os.environ['DJANGO_SETTINGS_MODULE'] = 'Shop.settings'
from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()

