"""Configuration WSGI du projet DataZen."""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "datazen.settings")

application = get_wsgi_application()
