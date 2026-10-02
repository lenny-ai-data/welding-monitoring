"""Point d'entrée : `gunicorn weldmon.app.main:server` en production, `python -m weldmon.app.main` en local."""

import os

from . import create_app

app = create_app()
server = app.server

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "8050")), debug=False)
