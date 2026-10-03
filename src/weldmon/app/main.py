"""Point d'entrée : `gunicorn weldmon.app.main:server` en production, `python -m weldmon.app.main` en local."""

import os

from . import create_app

# Application --------------------------------------------------------------------------------------
app = create_app()
server = app.server

# Préchauffage -------------------------------------------------------------------------------------
# Dash n'enregistre les bibliothèques de composants servables (/_dash-component-suites)
# qu'au premier rendu de la page, et ce par processus. Avec gunicorn (preload_app + plusieurs workers),
# on rend la page une fois dans le maître : chaque worker hérite du registre au fork, sinon le tout
# premier visiteur après un démarrage peut recevoir une page incomplète.
with server.test_client() as client:
    client.get("/")
    client.get("/_dash-layout")
    client.get("/_dash-dependencies")

# Lancement en local -------------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "8050")), debug=False)
