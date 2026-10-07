# TP 1 — Faire parler une API que personne ne documente

Serveur MCP `bibliotheque-municipale` : exploration, cinq missions, et un skill OpenCode
qui documente les pièges de l'API.

| Fichier | Contenu |
|---|---|
| [`RAPPORT.md`](RAPPORT.md) | réponses aux exercices 1 à 3, journal de bord des 5 missions, captures |
| [`.opencode/skills/bibliotheque-mcp/SKILL.md`](.opencode/skills/bibliotheque-mcp/SKILL.md) | **le skill** : 11 pièges de l'API + anomalies de données, recettes par mission |
| [`.opencode/skills/bibliotheque-mcp/scripts/biblio.py`](.opencode/skills/bibliotheque-mcp/scripts/biblio.py) | script fourni avec le skill : calculs des missions, lecture seule |
| [`opencode.json`](opencode.json) | déclaration du serveur MCP, sans token (`{env:…}`) |
| [`.env.example`](.env.example) | modèle des deux variables à fournir (le vrai `.env` est ignoré par Git) |
| [`captures/`](captures/) | captures du vrai OpenCode 1.18.35, intégrées au rapport |

## Lancer / vérifier

```bash
cp .env.example .env          # y mettre l'URL du serveur et le token
set -a; source .env; set +a
opencode                      # le skill est découvert dans .opencode/skills/

# recalcul des missions, lecture seule (Python 3, aucune dépendance)
python3 .opencode/skills/bibliotheque-mcp/scripts/biblio.py inventaire   # M1
python3 .opencode/skills/bibliotheque-mcp/scripts/biblio.py retards      # M2
python3 .opencode/skills/bibliotheque-mcp/scripts/biblio.py relance      # M5
python3 .opencode/skills/bibliotheque-mcp/scripts/biblio.py emprunts MB-202
```
