"""Configuration gunicorn de production (lue par l'image Docker)."""

import os

import gunicorn

# Identité du serveur ------------------------------------------------------------------------------
# Ne pas annoncer le serveur ni sa version dans l'en-tête « Server ».
gunicorn.SERVER = "weldmon"
gunicorn.SERVER_SOFTWARE = "weldmon"

# Processus : workers à threads, application chargée une fois dans le maître -----------------------
bind = f"0.0.0.0:{os.environ.get('PORT', '8050')}"
workers = int(os.environ.get("WEB_CONCURRENCY", "2"))
worker_class = "gthread"
threads = int(os.environ.get("GUNICORN_THREADS", "4"))
preload_app = True

# Délais et recyclage ------------------------------------------------------------------------------
timeout = 30
graceful_timeout = 20
keepalive = 5
max_requests = 2000  # recyclage régulier des workers
max_requests_jitter = 200

# Limites des requêtes -----------------------------------------------------------------------------
# Limites strictes sur la taille des requêtes (l'app n'accepte aucun upload).
limit_request_line = 4094
limit_request_fields = 50
limit_request_field_size = 8190

# Conteneur en lecture seule -----------------------------------------------------------------------
# Compatible --read-only : fichiers de battement des workers en mémoire.
worker_tmp_dir = "/dev/shm"

# Proxy et journaux --------------------------------------------------------------------------------
# En-têtes X-Forwarded-* acceptés uniquement depuis le reverse proxy déclaré.
forwarded_allow_ips = os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1")

accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("LOG_LEVEL", "info")
access_log_format = '%({x-forwarded-for}i)s "%(r)s" %(s)s %(b)s %(M)sms'
