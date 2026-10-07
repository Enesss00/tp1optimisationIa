# TP 1 — Faire parler une API que personne ne documente

Serveur MCP `bibliotheque-municipale` : exploration, cinq missions, et un skill OpenCode
qui documente les pièges de l'API.

## Où est quoi

| Fichier | Contenu |
|---|---|
| [`RAPPORT.md`](RAPPORT.md) | réponses aux exercices 1 à 3 et journal de bord des 5 missions |
| [`.opencode/skills/bibliotheque-mcp/SKILL.md`](.opencode/skills/bibliotheque-mcp/SKILL.md) | **le skill** : 12 pièges (outil / observation / réalité / règle) et recettes par mission |
| [`opencode.json`](opencode.json) | déclaration du serveur MCP, sans token (`{env:…}`) |
| [`.env.example`](.env.example) | modèle des deux variables à fournir (le vrai `.env` est ignoré par Git) |
| [`outils/verifier.py`](outils/verifier.py) | rejoue les preuves en **lecture seule** et recalcule les missions |
| [`outils/mcp_client.py`](outils/mcp_client.py) | client minimal pour rejouer n'importe quel appel du journal |
| [`journal/verification.txt`](journal/verification.txt) | sortie de `verifier.py` au moment du rendu (12/12 OK) |
| [`journal/00-tools-list.json`](journal/00-tools-list.json) | réponse brute de `tools/list` |
| `journal/appels-bruts.jsonl.gz` | tous les appels de l'exploration, horodatés, avec la réponse brute |
| [`captures/`](captures/) | captures d'écran OpenCode référencées dans le rapport |

## Vérifier en 2 minutes

Python 3 suffit (aucune dépendance).

```bash
cp .env.example .env        # puis y mettre l'URL du serveur et un token
set -a; source .env; set +a
python3 outils/verifier.py  # ~25 appels, ~30 s, aucune écriture
```

Chaque piège du skill est testé contre le serveur réel (`[OK ]` / `[ÉCHEC]`, avec la
réponse brute en preuve), puis les réponses des missions sont recalculées.
`python3 outils/verifier.py --bridage` ajoute la démonstration de P1 : une rafale
d'appels, puis les faux succès renvoyés pendant le bridage. Le token reste alors
bloqué environ une minute.

Rejouer un appel précis :

```bash
python3 outils/mcp_client.py list                                   # outils et schémas
python3 outils/mcp_client.py get_member_fees '{"member_id":"MB-225"}'
zcat journal/appels-bruts.jsonl.gz | grep '"tool": "create_loan"'   # retrouver un appel du journal
```

## Utiliser le skill dans OpenCode

```bash
set -a; source .env; set +a
opencode            # le skill est découvert dans .opencode/skills/ et chargé via l'outil `skill`
```

Le token n'apparaît nulle part dans l'historique Git (`git log -p | grep <token>` ne
renvoie rien).
