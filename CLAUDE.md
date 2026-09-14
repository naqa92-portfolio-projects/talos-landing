# Project: talos-landing

Landing page for `taloslab.cc` — Flask SSR + HTMX + TailwindCSS v4.

## Stack

- **Backend**: Flask + Gunicorn
- **Frontend**: Jinja2 SSR + HTMX + TailwindCSS v4 + AlpineJS
- **Data**: Kubernetes API — nodes, metrics, ArgoCD Applications, Crossplane XR Apps, HTTPRoutes
- **Design**: palette « Xénon » — tokens dans `app/static/css/input.css`, source de vérité dans le skill `/youtube-identity` (`references/design-tokens.json`)

## TailwindCSS

TailwindCSS v4 standalone CLI (no Node required). `app/static/css/style.css` est committé :
devbox est son seul producteur, la CI ne le reconstruit pas.

```bash
devbox run css:build   # Build minifié — à relancer après toute modification de classes
devbox run css:watch   # Watch mode
```

## Development

```bash
uv sync
devbox run dev                        # TALOS_MOCK=1 — fixtures, aucun cluster requis
uv run flask --app app run --debug    # contre le vrai cluster (kubeconfig courant)
```

## Docker

```bash
docker build -t talos-landing .
docker run -p 8000:8000 talos-landing
```
