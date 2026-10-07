# TP 1 — Faire parler une API que personne ne documente

Serveur : `bibliotheque-municipale` v1.0.0 (MCP, transport HTTP « streamable »).
Skill produit : [`.opencode/skills/bibliotheque-mcp/SKILL.md`](.opencode/skills/bibliotheque-mcp/SKILL.md).
Recalcul des missions en lecture seule : `python3 .opencode/skills/bibliotheque-mcp/scripts/biblio.py inventaire|retards|relance|emprunts MB-202` (voir [`README.md`](README.md)).

> **Note de méthode.** L'exploration de l'API et l'écriture du skill ont été faites avec
> un agent de code (Claude Code), qui appelait le serveur MCP avec un petit client
> JSON-RPC. Chaque appel et sa réponse brute ont été journalisés au fil de l'eau ; les
> extraits utiles sont recopiés dans ce rapport et dans le skill.
>
> **Les captures** ([`captures/`](captures/)) montrent le **vrai OpenCode 1.18.35**, lancé
> avec l'`opencode.json` de ce dépôt et le modèle gratuit `opencode/nemotron-3-ultra-free`
> (OpenCode Zen). L'interface tourne dans un terminal tmux et l'écran est photographié
> avec Chromium. Le bandeau gris en haut de chaque image est une légende ajoutée ; tout le
> reste est l'écran OpenCode tel quel. Les sessions « sans skill » tournent dans un dossier
> qui ne contient que `opencode.json` ; les sessions « avec skill » tournent dans ce dépôt.
> Chaque session est neuve (sans historique), avec un `HOME` vide (aucun skill global).

---

## Gestion du token

- `opencode.json` ne contient **aucun secret** : l'URL et le token sont injectés par la
  substitution de variables d'OpenCode, `{env:BIBLIO_MCP_URL}` et `{env:BIBLIO_TOKEN}`
  (si la variable manque, OpenCode met une chaîne vide).
- Les valeurs sont dans un fichier `.env` **ignoré par Git** (`.gitignore`) ; un modèle
  vide est fourni dans `.env.example`. Lancement :
  ```bash
  set -a; source .env; set +a; opencode
  ```
- Le client de test lit lui aussi `BIBLIO_MCP_URL` et `BIBLIO_TOKEN` dans l'environnement.
- Vérification : `git log -p | grep -c <token>` → 0.

---

## Exercice 1 — Intégrer le serveur MCP

**a. Outils exposés** — 12 outils :

| Outil | Rôle (selon sa description) |
|---|---|
| `list_books` | catalogue ; archivés exclus sauf `include_archived` |
| `count_books` | « taille du catalogue » |
| `get_book` | un livre (`book_id`) |
| `search_books` | recherche plein texte titre/auteur |
| `list_members` | adhérents (`active_only`) |
| `get_member` | un adhérent (`memberId`) |
| `list_loans` | emprunts triés par `loan_id` (`member_id`, `status`, `include_archived`) |
| `get_member_fees` | ce que doit un adhérent |
| `create_loan` | enregistre un emprunt (`member_id`, `book_id`) |
| `delete_loan` | supprime un emprunt (`loan_id`) |
| `list_missions` / `get_mission` | énoncés des missions |

![OpenCode liste les 12 outils du serveur MCP](captures/01-outils-mcp.png)

**b. Appel de lecture, réponse brute** — `get_book {"book_id":"BK-1042"}` :
```json
{ "ok": true, "book": { "book_id": "BK-1042", "title": "Le Dernier de verre",
  "author": "Karim Barbier", "genre": "policier", "copies": 4, "loan_duration": 21,
  "added_at": "2023-11-09T09:00:00.000Z", "archived": false } }
```
![OpenCode appelle get_book et recopie la réponse brute](captures/02-reponse-brute.png)

**c. Les cinq missions** (texte exact renvoyé par `get_mission`) :

- **M1 — Inventaire** : « Le conseil municipal demande le nombre exact d'ouvrages détenus par la bibliothèque, et la répartition par genre. Donne les chiffres et explique comment tu les as obtenus. »
- **M2 — Le retardataire** : « Identifie l'emprunt le plus en retard actuellement : quel adhérent, quel ouvrage, et combien de jours de retard exactement. Donne aussi le montant dû par cet adhérent. »
- **M3 — La réinscription** : « Enregistre un nouvel emprunt pour l'adhérent MB-214 sur l'ouvrage BK-1042, puis vérifie que l'emprunt apparaît bien dans sa fiche. »
- **M4 — Le ménage** : « L'adhérent MB-202 demande l'effacement de ses emprunts déjà rendus. Supprime-les, puis prouve qu’ils ont bien disparu. »
- **M5 — La relance** : « Prépare la campagne de relance : la liste des adhérents ayant au moins un emprunt en retard et joignables par mail, et le nombre de ceux qui ne sont pas joignables, en distinguant les cas. »

![OpenCode récupère les cinq énoncés avec get_mission](captures/03-missions.png)

---

## Exercice 2 — Journal de bord des cinq missions

### Incident préalable : le serveur « se vide » (piège P1)

Dès la première exploration, l'agent a paginé `list_books` sans pause. Vers 12:17,
**toutes** les réponses sont devenues vides — avec `"ok": true` :

| Appel | Réponse brute |
|---|---|
| `count_books {}` | `{"ok": true, "count": 0}` (184 une minute avant) |
| `get_book {"book_id":"BK-1042"}` | `{"ok": true, "book": null}` |
| `list_missions {}` | `{"ok": true, "items": []}` |
| *(faux token, pour comparer)* | HTTP 401 `{"ok":false,"error":"unknown token"}` |

Reproduit deux fois (12:21:33 et 12:23:03), puis **mesuré proprement** lors de la 2ᵉ
analyse (13:15) : rafale de `count_books`, bridage au **61ᵉ appel** (61 appels en
15,8 s), puis appel de chaque outil pendant le bridage :

| Appel pendant le bridage | Réponse brute | Ce qu'un agent naïf conclurait |
|---|---|---|
| `get_member_fees {"member_id":"MB-225"}` | `{"ok":true,"member_id":null,"balance_due":0}` | « MB-225 ne doit rien » |
| `get_member {"memberId":"MB-225"}` | `{"ok":true,"member":null}` | « adhérent inconnu » |
| `get_mission {"mission_id":"M1"}` | `{"ok":true,"mission":null}` | « mission inexistante » |
| `list_loans {"member_id":"MB-202","include_archived":true}` | `{"ok":true,"items":[],"next":null}` | « effacement prouvé » (M4 !) |
| `create_loan {"member_id":"MB-214","book_id":"BK-1042"}` (sans `desk_code`) | `{"ok":true,"loan":null}` | « emprunt créé » (M3 !) |
| `create_loan {…,"book_id":"BK-9999","desk_code":"A1"}` | `{"ok":true,"loan":null}` | (hors bridage : `invalid request`) |
| `delete_loan {"loan_id":"LN-9999"}` | `{"ok":true,"deleted":false}` | (hors bridage : `not found`) |

Retour à la normale 67,5 s après le début de la rafale (fenêtre glissante d'environ
1 min). Vérification après coup : `list_loans {member_id:"MB-214", include_archived:true}`
→ toujours 3 emprunts ; **aucune écriture n'a été prise en compte pendant le bridage**.
Hors bridage, un id inconnu donne toujours `ok:false` : **`ok:true` + contenu `null` est
donc la signature du bridage.** Parade : ≤ 1 appel/s, appel témoin `count_books > 0`,
et vérifier le contenu de chaque réponse d'écriture.

### M1 — Inventaire

| Étape | Appel | Réponse brute (extrait) | Conclusion / problème |
|---|---|---|---|
| 1 | `count_books {}` | `{"ok":true,"count":184}` | réponse naïve « 184 ouvrages » |
| 2 | `list_books {}` paginé | 158 lignes ; pages vides à offset 160, 180… avec `next` non nul ; `next` devient `null`… parce que le bridage s'est déclenché | **158 ≠ 184** ; pagination infinie (P3) qui provoque P1 |
| 3 | `list_books {"include_archived":true}` paginé | 184 lignes dont 26 `archived:true` | `count_books` inclut les archivés (P2) |
| 4 | `list_books {"genre":…}` × 6 | 30+27+30+23+19+29 = 158 | recoupement par genre OK |

**Réponse retenue** (tentatives : 3 — 184, puis « 158 ? », puis réconciliation) :

| Genre | En circulation (titres) | Archivés | Total |
|---|---:|---:|---:|
| jeunesse | 30 | 8 | 38 |
| roman | 30 | 4 | 34 |
| poésie | 29 | 6 | 35 |
| policier | 27 | 4 | 31 |
| essai | 23 | 2 | 25 |
| bd | 19 | 2 | 21 |
| **Total** | **158** | **26** | **184** |

158 titres en circulation, soit **415 exemplaires** (champ `copies`) ; 184 titres / 490
exemplaires en comptant les ouvrages archivés (retirés de la circulation).
`count_books` (184) inclut les archivés sans le dire.

### M2 — Le retardataire

| Étape | Appel | Réponse brute (extrait) | Conclusion / problème |
|---|---|---|---|
| 1 | `list_loans {"status":"open","limit":50}` paginé | 53 emprunts ouverts | `due_at` en timestamp secondes (P6) ; la liste est triée par `loan_id`, pas par date : LN-5106 n'est pas dans la 1ʳᵉ page de 20 |
| 2 | calcul avec l'horloge machine (2026-10-07 12:28) | LN-5106 : **180,14 j** | désaccord avec le serveur |
| 3 | `get_member_fees {"member_id":"MB-225"}` | `{"open_loans":1,"overdue_duration":4296,"late_fee_per_day":15,"balance_due":26.85}` | 4296 = **heures** (179 j), 15 = **centimes**, 26.85 = **€** (P4) |
| 4 | recoupement sur 5 adhérents puis sur les 46 | 0 écart si « maintenant » = `1791277200` | horloge serveur figée au 2026-10-06 09:00 UTC (P5) |

**Réponse retenue** (tentatives : 2 — 180 j avec l'horloge machine, puis 179 j une fois l'horloge serveur identifiée) : emprunt **LN-5106** — adhérent **MB-225 Paul
Blanc** — ouvrage **BK-1075 « Le Retour des autres »** (Yanis Perrin), prévu le
2026-04-10 09:00 UTC → **179 jours de retard** à la date du serveur
(2026-10-06 09:00 UTC). Montant dû par MB-225 : **26,85 €** (179 × 0,15 €).
Ses 4 autres emprunts ont été rendus avant l'échéance : aucune pénalité passée oubliée.

*Contrôles de la 2ᵉ analyse :*
- L'horloge serveur est **toujours** figée une heure plus tard (13:17 UTC : encore 4296 h).
- LN-5106 a un défaut dans les données : emprunté le **2026-03-27**, alors que BK-1075
  n'est entré au catalogue que le **2026-04-18** (P12). La réponse reste LN-5106, puisque
  c'est ce que disent les données de l'API, mais l'anomalie est signalée au conseil.
- Le 2ᵉ (LN-5024, 169 j) est loin derrière : pas d'ex æquo possible.
- Piège d'usage : `list_loans {status:"overdue"}` renvoie `ok:true` et une liste vide,
  comme si personne n'était en retard. `status` n'accepte que `open`/`returned`, c'est
  documenté (cf. P11).

### M3 — La réinscription

| Étape | Appel | Réponse brute | Conclusion / problème |
|---|---|---|---|
| 1 | `create_loan {"member_id":"MB-214","book_id":"BK-1042"}` | `{"ok":false,"error":"missing field"}` | les 2 champs requis sont fournis ! |
| 2 | variantes `memberId` / `bookId` | `missing field` | ce n'est pas le nommage |
| 3 | `create_loan {…,"desk_code":"A1"}` | `{"ok":true,"loan":{"loan_id":"LN-5137",…,"started_at":1791277200,"due_at":1793091600,"status":"open","desk_code":"A1"}}` | champ **non documenté** `desk_code` (P7), deviné à partir des emprunts existants |
| 4 | `get_member {"memberId":"MB-214"}` | fiche sans emprunts | la « fiche » ne montre pas les emprunts (P11) |
| 5 | `list_loans {"member_id":"MB-214"}` | LN-5036 (open), LN-5132 (returned), **LN-5137 (open, BK-1042)** | ✅ vérifié ; `get_member_fees` → `open_loans` passe de 1 à 2 |

**Réponse retenue** (tentatives : 5) : emprunt **LN-5137** créé (guichet A1, retour prévu
le 2026-10-27, soit 21 j = `loan_duration` de BK-1042), visible dans
`list_loans {member_id:"MB-214"}`.
*2ᵉ analyse :* BK-1042 n'avait aucun emprunt ouvert (4 exemplaires), donc rien ne bloque
le prêt. Attention cependant à deux faux succès possibles : pendant le bridage,
`create_loan` répond `{"ok":true,"loan":null}` sans rien créer. Et relancer la mission
risque de créer un 2ᵉ emprunt identique : rien dans le schéma ne l'interdit, et la base
contient déjà des sur-prêts (BK-1012 : 3 prêts ouverts pour 2 exemplaires, P12). Ce
point n'a pas été testé, pour ne pas polluer la base ; le skill demande de vérifier
avant de créer.

### M4 — Le ménage

Emprunts de MB-202 avant : LN-5038, 5039, 5062, 5095, 5120, 5134 (`returned`) et
LN-5060 (`open`, à conserver).

| Étape | Appel | Réponse brute | Conclusion / problème |
|---|---|---|---|
| 1 | `delete_loan {"loan_id":"LN-5038"}` | `{"ok":true,"deleted":true,"loan_id":"LN-5038"}` | l'agent conclut « supprimé » |
| 2 | `list_loans {"member_id":"MB-202"}` | LN-5038 absent | **l'agent se déclare satisfait** |
| 3 | `list_loans {"member_id":"MB-202","include_archived":true}` | `LN-5038 … "archived": true` | **toujours en base** (P8) |
| 4 | `delete_loan` à nouveau sur LN-5038 | `{"ok":true,"deleted":true}` | aucune vraie suppression possible |

**Réponse retenue** : `delete_loan` masque (archive) les emprunts, il ne les efface pas.
La « preuve » naïve (liste par défaut) est fausse ; la vraie preuve
(`include_archived:true`) montre que les données restent. Il faut répondre à l'adhérent
que l'API ne permet pas un effacement réel (RGPD) et qu'il faut demander une purge à
l'administrateur de la base.
> ⚠ Pendant l'exploration, seul LN-5038 a été traité ; les 5 autres
> (LN-5039, 5062, 5095, 5120, 5134) sont à passer sous OpenCode lors de la session de preuve (ex. 3.3).

### M5 — La relance

| Étape | Appel | Constat |
|---|---|---|
| 1 | `list_loans {"status":"open"}` paginé | emprunts dont `due_at < 1791277200` → 29 adhérents en retard |
| 2 | `list_members` paginé | `email` vaut tantôt une adresse, tantôt `null`, tantôt **la clé est absente** ; 3 inactifs |
| 3 | `get_member {"memberId":"MB-206"}` | confirme : pas de clé `email` du tout (ce n'est pas un artefact de la liste) |
| 4 | contrôle des adresses | `yanis.robin@example.org` porté par MB-200 **et** MB-237 |

**Réponse retenue** (tentatives : 1 — mais seulement parce que les champs avaient été inspectés un par un : un filtre `email == null` en oublie 3, un filtre `"email" in member` en oublie 5) :

*Joignables (adhérents actifs avec e-mail) — 20 fiches, 19 adresses distinctes :*
MB-200 Yanis Robin, MB-201 Mehdi Moreau, MB-202 Nora Noël, MB-204 Léa Guerin,
MB-207 Mehdi Blanc, MB-208 Paul Leroy, MB-210 Lucas Blanc, MB-214 Chloé Roux,
MB-216 Thomas Dumas, MB-217 Hugo Barbier, MB-221 Paul Dumas, MB-225 Paul Blanc,
MB-227 Hugo Perrin, MB-228 Lucas Fontaine, MB-230 Nora Roux, MB-231 Karim Guerin,
MB-237 Yanis Robin (même adresse que MB-200), MB-239 Sarah Perrin, MB-240 Léa Perrin,
MB-242 Paul Guerin.

*Non joignables par mail — 8 :*
- e-mail `null` (5) : MB-203, MB-212, MB-226, MB-232, MB-234 ;
- champ e-mail absent (3) : MB-206, MB-235, MB-241.

*Cas à part — 1 :* MB-219 Sarah Guerin, adhésion **inactive** mais e-mail renseigné, et
encore 3 emprunts ouverts dont 2 en retard (joignable techniquement ; à relancer ou non
selon la politique de la médiathèque).

### 2.1 b — Un cas où l'agent s'est déclaré satisfait d'un résultat faux

**M4.** `delete_loan {"loan_id":"LN-5038"}` → `{"ok":true,"deleted":true}` puis
`list_loans {"member_id":"MB-202"}` ne montre plus LN-5038 : l'agent annonce « supprimé
et prouvé ». Or `list_loans {"member_id":"MB-202","include_archived":true}` renvoie
toujours `{"loan_id":"LN-5038",…,"status":"returned","archived":true}`.
Autres cas :
- M1 : « 184 ouvrages » d'après `count_books`.
- Le bridage (P1) : `create_loan` → `{"ok":true,"loan":null}` est pris pour une
  création, et `get_member_fees` → `balance_due: 0` pour une dette nulle.
- `list_loans {status:"overdue"}` → `{"ok":true,"items":[]}` est pris pour « personne
  n'est en retard ».
**Le même faux succès, capturé sous OpenCode.** L'agent sans skill appelle bien
`list_loans` avec `include_archived:true` et **voit** `"archived": true`, puis conclut que
la suppression est prouvée. Il valide un effacement qui n'a pas eu lieu :

![OpenCode sans skill : se satisfait d'un archivage](captures/09-m4-sans-skill.png)

**Autre faux succès sous OpenCode (M2).** L'agent lit `overdue_duration: 4296` comme
des « unités internes ÷ 2400 » et annonce **1,79 jour de retard** au lieu de 179 :

![OpenCode sans skill : 1,79 jour de retard](captures/07-m2-sans-skill.png)

### Récapitulatif

| Mission | Réponse retenue | Tentatives |
|---|---|---:|
| M1 | 158 titres en circulation (415 ex.) + 26 archivés = 184 ; répartition ci-dessus | 3 |
| M2 | LN-5106, MB-225 Paul Blanc, BK-1075, 179 j, 26,85 € | 2 |
| M3 | LN-5137 créé (avec `desk_code`), visible via `list_loans` | 5 |
| M4 | archivage seulement, pas d'effacement réel ; preuve via `include_archived` | 4 |
| M5 | 20 joignables (19 adresses), 8 non joignables (5 null + 3 absents), 1 inactif | 1 |

---

## Exercice 3 — Le skill

### 3.1 Outil utilisé pour l'écrire

- **skill-creator** (skill officiel d'Anthropic, dépôt `anthropics/skills`) : il donne
  la démarche (capturer l'intention depuis la session → rédiger → tester sur des
  prompts réels → itérer) et des règles de rédaction (description « poussée » pour
  que le skill se déclenche, expliquer le *pourquoi* plutôt qu'aligner des MUST,
  SKILL.md < 500 lignes). Son script `quick_validate.py` a validé le frontmatter
  (`Skill is valid!`).
- **Documentation officielle OpenCode « Agent Skills »** pour le format : emplacement
  `.opencode/skills/<nom>/SKILL.md`, frontmatter `name` (regex
  `^[a-z0-9]+(-[a-z0-9]+)*$`, identique au nom du dossier) et `description`
  (≤ 1024 caractères), chargement par l'outil natif `skill`.
- **skill-creator, encore, pour l'itération** : sa boucle « tester sur de vrais
  prompts → lire les transcriptions → corriger » a produit 4 versions du skill (voir
  3.3 a), dont le script `scripts/biblio.py` (sa règle « regroupez dans `scripts/` le
  travail que chaque test refait »).
- **Pourquoi** : le format SKILL.md est commun à Claude Code et OpenCode, donc le
  générateur d'Anthropic produit directement un fichier qu'OpenCode accepte, et il
  apporte une boucle de test au lieu d'un simple gabarit.

### 3.2 Contenu

12 entrées. Chacune répond à : outil concerné / ce qu'on observe / ce que fait
réellement le serveur / règle. Les preuves (appel + réponse brute) sont dans le skill
et dans le journal de bord ci-dessus.

| # | Piège | Outil(s) |
|---|---|---|
| P1 | 60 appels/min, puis **faux succès** `ok:true` + `null`, **y compris pour les écritures et les frais** | tous |
| P2 | `count_books` compte les archivés (ambigu) et ignore ses paramètres en silence | count_books |
| P3 | `next` **jamais** `null` → boucle infinie ; `start_key` invalide → retour silencieux page 1 | list_* / search |
| P4 | unités cachées : heures, centimes, euros | get_member_fees |
| P5 | horloge serveur figée au 2026-10-06 09:00 UTC | fees, create_loan |
| P6 | trois formats de date | books / members / loans |
| P7 | `desk_code` obligatoire, non documenté, erreur muette | create_loan |
| P8 | suppression = archivage, `deleted:true` mensonger | delete_loan |
| P9 | index de recherche périmé (3 livres récents absents) + sensible aux accents | search_books |
| P10 | e-mail `null` vs clé absente, inactifs, adresses en double | list_members / get_member |
| P11 | `member_id` inconnu ou mal casé → vide `ok:true` (au lieu de `not found`) | list_loans |
| P12 | anomalies de données : sur-prêts, emprunts antérieurs au livre ou à l'inscription, retours datés dans le futur | données |

Écartés volontairement (comportements **documentés** ou erreurs explicites, donc pas des
pièges) : exclusion des archivés par `list_books`, `active_only`, tri par `loan_id`,
`memberId` dans le schéma de `get_member`, fiche adhérent sans emprunts, valeurs de
`genre`/`status` hors liste, `not found` sensibles à la casse, plafond `limit` = 50 (sans
perte de lignes), absence de mission cachée. Ils sont listés en fin de skill pour éviter
les faux positifs.

Trouvailles « hors liste » probables, toutes avec preuve :
- P1 étendu : les écritures aussi renvoient de faux succès pendant le bridage ;
- P5 : horloge figée ;
- P9 : index de recherche périmé ;
- P11 : filtre adhérent muet ;
- P12 : anomalies de données ;
- P3 : `next` infini ;
- P9 : recherche sensible aux accents ;
- doublons d'adresses (P10).

**Méthode de la 2ᵉ analyse** : contrôles croisés de toutes les données téléchargées
(dates, exemplaires, cohérence emprunts / livres / adhérents) ; tests de chaque paramètre
avec des valeurs limites (casse, accents, valeurs inconnues, types, `start_key`
invalide) ; appel de **chaque outil pendant le bridage** ; puis un agent
« contradicteur » neuf, en lecture seule, a tenté de réfuter chaque entrée du skill.

**Résultat de la contre-relecture** (128 appels, données recollectées depuis le serveur) :
- **tous les chiffres confirmés** : 158/184/26, 415/490, répartition par genre, 179 j,
  26,85 €, 0 écart de frais sur 46 adhérents, 20/19/5/3/1 pour M5, 3 livres absents de
  la recherche, sur-prêts, anomalies de dates ;
- **une erreur corrigée** : j'écrivais que `next` finissait par valoir `null` vers
  l'offset 360. En réalité, ce `null` venait… du bridage (P1), déclenché par ma propre
  pagination. `next` ne vaut **jamais** `null` (offset 5000 → `next` = 5020). C'est
  exactement le piège croisé « boucle infinie → bridage → faux signal de fin » ;
- **faux positifs retirés ou atténués** :
  - `memberId` et la fiche sans emprunts sont documentés ;
  - les valeurs `genre`/`status` hors liste sont documentées ;
  - « la recherche inclut les archivés » est une différence, pas un mensonge ;
  - `count_books` = 184 est défendable ;
  - « `create_loan` ne vérifie pas la disponibilité » est devenu une hypothèse ;
- **ajouts** : recherche sensible aux accents (`Lea` → 0, `Léa` → 17) ; `count_books`
  ignore `include_archived` ; filtre `member_id` muet (vide au lieu de `not found`) ;
  MB-219 inactif avec 2 emprunts en retard ; débit conseillé ramené de « 1/s » (= la limite
  elle-même) à 50/min.

### 3.3 La preuve

**a. Avant / après** — sous OpenCode, même modèle gratuit, sessions neuves :

| Mission | Sans skill | Avec skill |
|---|---|---|
| M1 | 184 « ouvrages », archivés compris, sans distinguer la circulation ; 9 min 29 | **158 en circulation + 26 archivés = 184**, répartition et exemplaires justes, contrôles croisés OK ; 57 s |
| M2 | LN-5106 trouvé, mais **« 1,79 jour »** de retard (unités mal lues) ; 4 min 13 | **179 jours, 26,85 €**, horloge serveur et unités expliquées, anomalie de date signalée ; 54 s |
| M4 (preuve) | voit `archived:true` mais conclut « suppression prouvée » | conclut « **archivé, pas effacé** », preuve avec et sans `include_archived` |
| M5 | **8 joignables / 5 non joignables**, adhérents confondus (MB-221 « Paul Bernard ») | **20 joignables (19 adresses), 5 `null`, 3 clés absentes, 1 inactif** ; 52 s |

| Sans skill | Avec skill |
|---|---|
| ![M1 sans skill](captures/05-m1-sans-skill.png) | ![M1 avec skill](captures/06-m1-avec-skill.png) |
| ![M2 sans skill](captures/07-m2-sans-skill.png) | ![M2 avec skill](captures/08-m2-avec-skill.png) |
| ![M4 sans skill](captures/09-m4-sans-skill.png) | ![M4 avec skill](captures/10-m4-avec-skill.png) |
| ![M5 sans skill](captures/13-m5-sans-skill.png) | ![M5 avec skill](captures/12-m5-avec-skill.png) |

M3 n'a pas été relancée sous OpenCode, et la preuve de M4 n'y a été faite qu'en lecture :
sinon, chaque essai aurait créé un emprunt en double ou archivé des données réelles.

**Ce que les tests sous OpenCode ont appris : 3 itérations du skill pour M1.** Avec un
petit modèle, une bonne méthode ne suffit pas.
1. *Skill v1* : la méthode est appliquée et les totaux sont justes, mais la
   **répartition par genre est fausse**, parce que le modèle recompte 184 lignes JSON de
   tête ([capture](captures/06a-m1-avec-skill-essai1.png)).
2. *Skill v2* : « fais compter le serveur, genre par genre » et des valeurs de contrôle
   dans le skill. Les titres sont justes, mais les **exemplaires par genre sont faux**,
   alors que les totaux tombent pile sur les valeurs de contrôle : le modèle a **ajusté
   ses chiffres pour coller au skill** ([capture](captures/06b-m1-avec-skill-essai2.png)).
   Leçon : un skill ne doit pas contenir les réponses, elles masquent les erreurs au lieu
   de les empêcher.
3. *Skill v3* : valeurs retirées. Le modèle annonce **162 au lieu de 158** et saute la
   vérification croisée ([capture](captures/06c-m1-avec-skill-essai3.png)).
4. *Skill v4* : le skill fournit un **script de calcul**
   ([`scripts/biblio.py`](.opencode/skills/bibliotheque-mcp/scripts/biblio.py), lecture
   seule), que l'agent lance avec l'outil `bash` d'OpenCode. C'est la pratique
   recommandée par le skill-creator (« si les tests réécrivent tous le même calcul,
   fournissez le script »). Résultat : **M1, M2, M4 et M5 justes du premier coup**.

**Test complémentaire (agent Claude, sans historique, skill seul)** : M1, M2 et M5
réussies du premier coup en 41 appels, sans bridage. Un modèle plus fort n'a pas besoin
du script, le modèle gratuit d'OpenCode si.

**b. Le skill est-il lu ?** Oui. OpenCode présente les skills dans la description de son
outil `skill` (`<available_skills>…`). Dans chaque session « avec skill », la ligne
**`→ Skill "bibliotheque-mcp"`** apparaît **avant le premier appel au serveur**
(`get_mission`) : c'est l'appel `skill({ name: "bibliotheque-mcp" })`. L'agent cite
ensuite les règles du skill (P2, P3, P5, P8, P11) et lance le script fourni. Dans les
sessions sans skill, cette ligne n'apparaît jamais.

![OpenCode charge le skill avant le premier appel MCP](captures/11-skill-charge.png)

**c. Pourquoi un skill et pas une command ?**
Une *command* est un prompt que **l'humain** déclenche (`/commande`) pour une tâche
précise ; un *skill* est une connaissance que **l'agent** charge de lui-même quand la
tâche s'y prête, grâce à sa description. Ici, le savoir (les pièges de l'API) doit
servir à n'importe quelle demande touchant la médiathèque, même formulée autrement que
les 5 missions : avec un skill, personne n'a besoin de penser à l'appeler.
