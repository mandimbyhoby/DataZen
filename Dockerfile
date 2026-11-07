# syntax=docker/dockerfile:1
#
# Image de production DataZen : Django 5.2 + Waitress + WhiteNoise.
#
#   docker build -t datazen .
#   docker run --rm -p 8000:8000 --env-file .env datazen
#
# Pour un démarrage complet (application + PostgreSQL), utiliser plutôt
# `docker compose up -d --build` (voir docker-compose.yml).

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=datazen.settings \
    PYTHONPATH=/app

# Polices système : matplotlib n'embarque pas les glyphes CJK, thaï, devanagari
# ou arabes. Sans elles, les libellés des graphiques s'affichent en carrés pour
# 8 des 23 langues de l'interface (ar, hi, ja, ko, ru, th, vi, zh_hans).
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        fonts-noto-core \
        fonts-noto-cjk \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Les dépendances sont copiées seules pour profiter du cache de couches :
# une modification du code ne réinstalle pas les paquets.
#
# L'installation se fait depuis requirements.lock.txt avec --require-hashes :
# pip vérifie alors le SHA-256 de chaque archive téléchargée. Une dépendance
# substituée (paquet compromis, miroir malveillant) fait échouer la
# construction au lieu d'entrer silencieusement dans l'image.
COPY requirements.txt requirements.lock.txt ./
RUN pip install --no-cache-dir --require-hashes -r requirements.lock.txt

COPY . .

# collectstatic doit s'exécuter avec DEBUG=0 pour produire le manifeste attendu
# par CompressedManifestStaticFilesStorage (STORAGES dans datazen/settings.py).
# La clé ci-dessous ne sert qu'à la construction : elle est remplacée au
# démarrage par la valeur de DJANGO_SECRET_KEY fournie par l'environnement.
RUN DJANGO_DEBUG=0 \
    DJANGO_DB_ENGINE=sqlite \
    DJANGO_SECRET_KEY=build-time-only-key-not-used-at-runtime-0123456789 \
    python manage.py collectstatic --noinput --clear

# Utilisateur non privilégié : le processus WSGI n'a aucune raison de tourner
# en root. L'uid 1000 correspond au premier compte utilisateur Linux standard.
RUN useradd --create-home --uid 1000 --shell /bin/bash datazen \
 && mkdir -p /app/media \
 && chown -R datazen:datazen /app/media
USER datazen

EXPOSE 8000

# Point d'entrée en Python (et non en shell) : insensible aux fins de ligne
# CRLF produites par un checkout Windows (core.autocrlf=true).
# `-m docker.entrypoint` (et non le chemin du fichier) : exécuter un script par
# son chemin place son dossier dans sys.path, pas la racine du projet, et
# `import datazen` échouerait.
ENTRYPOINT ["python", "-m", "docker.entrypoint"]
CMD ["python", "-m", "waitress", "--listen=0.0.0.0:8000", "--threads=8", "datazen.wsgi:application"]
