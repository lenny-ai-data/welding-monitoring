"""Onglets de l'application, un module par section de la barre latérale.

Chaque module expose `layout()` (appelé une fois par create_app) et déclare ses callbacks à l'import.
Il doit pouvoir s'importer sans app_data/ (CI) : les données ne sont lues que dans les fonctions.
Ajout d'un onglet : voir docs/application.md.
"""
