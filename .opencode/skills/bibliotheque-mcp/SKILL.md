---
name: bibliotheque-mcp
description: Pièges et mode d'emploi du serveur MCP « bibliotheque-municipale » (outils list_books, count_books, get_book, search_books, list_members, get_member, list_loans, get_member_fees, create_loan, delete_loan, list_missions, get_mission). À charger AVANT tout appel à ce serveur, dès qu'il est question de la médiathèque, de son catalogue, de ses adhérents, emprunts, retards, pénalités, relances, ou des missions M1 à M5 — même si la tâche paraît simple. L'API ment sans renvoyer d'erreur ; ce skill dit où et comment s'en protéger.
license: MIT
compatibility: opencode
metadata:
  serveur: bibliotheque-municipale 1.0.0
  verifie-le: "2026-10-07"
---

# Serveur MCP « bibliotheque-municipale » — ce que la documentation ne dit pas

Cette API est vieille et incohérente. Sa propriété la plus dangereuse : **elle répond
`"ok": true` même quand ce qu'elle renvoie est faux ou vide.** Une absence d'erreur ne
prouve rien. Lis toujours le JSON brut, et recoupe chaque chiffre par un second chemin
avant de l'annoncer.

Les pièges ci-dessous ont tous été reproduits (appel exact + réponse brute). Chacun
répond à quatre questions : **outil**, **ce qu'on observe**, **ce que fait vraiment le
serveur**, **règle**.

---

## 0. Méthode générale (à appliquer à chaque mission)

1. **Débit ≤ 50 appels/minute** (un appel toutes les 1,2 s) : la limite est 60, et un
   appel par seconde tombe pile dessus (voir P1).
2. **Pagination** : `next` ne vaut **jamais** `null`. Arrête-toi à la **première page qui
   contient moins de `limit` lignes** (voir P3).
   Prends `limit: 50` (le maximum effectif) pour économiser des appels.
3. **`ok: true` ne prouve rien.** Un contenu `null` ou vide avec `ok: true` signifie
   « bridé » (P1) ou « filtre qui ne correspond à rien » (P11), jamais « n'existe pas » : le vrai
   « n'existe pas » est `ok: false, error: "not found"`. Avant de conclure à un vide,
   fais un appel témoin (`count_books` > 0) et refais l'appel sans filtre.
4. **Ne compte jamais de tête.** Sur des dizaines de lignes JSON, un modèle se trompe
   (observé : 34 romans annoncés au lieu de 30, 462 exemplaires au lieu de 415). Fais
   compter le serveur (un filtre par valeur) ou écris un petit script (Python/jq) sur
   les réponses brutes enregistrées.
5. **Recoupe** : un total se vérifie par deux chemins (compteur vs liste paginée, somme
   par genre vs total, frais serveur vs calcul à partir des emprunts).
6. **Après toute écriture**, relis l'état avec `list_loans` *avec et sans*
   `include_archived: true`.

---

## 1. Pièges

### P1 — Limitation de débit silencieuse, y compris sur les écritures (TOUS les outils)
- **Observé** : au **61ᵉ appel** d'une rafale (61 appels en 15,8 s), le serveur cesse de
  répondre vraiment, sans erreur ni HTTP 429 ni en-tête de quota :
  | Appel pendant le bridage | Réponse brute |
  |---|---|
  | `count_books {}` | `{"ok": true, "count": 0}` |
  | `list_*` / `search_books` | `{"ok": true, "items": [], "next": null}` |
  | `get_book {"book_id":"BK-1075"}` | `{"ok": true, "book": null}` |
  | `get_member {"memberId":"MB-225"}` | `{"ok": true, "member": null}` |
  | `get_mission {"mission_id":"M1"}` | `{"ok": true, "mission": null}` |
  | `get_member_fees {"member_id":"MB-225"}` | `{"ok": true, "member_id": null, "balance_due": 0}` |
  | `create_loan {…}` (même sans `desk_code`, même avec un livre inexistant) | `{"ok": true, "loan": null}` — **rien n'est créé** |
  | `delete_loan {"loan_id":"LN-9999"}` (inexistant) | `{"ok": true, "deleted": false}` |
- **Réalité** : environ **60 appels par fenêtre glissante d'une minute** par token. Au-delà,
  chaque outil renvoie un « succès » vide. Ça revient tout seul environ 60 s après le début
  de la rafale. L'horloge serveur n'y est pour rien. Hors bridage, un id inconnu donne
  `{"ok": false, "error": "not found"}` et un appel invalide donne
  `{"ok": false, "error": "invalid request"}`.
- **Signature à reconnaître** : `"ok": true` **avec un contenu `null`** (`book`, `member`,
  `mission`, `loan`, `member_id`) ou `count: 0` signifie « bridé », jamais « absent ».
  Le vrai « absent » est toujours `ok: false`.
- **Règle** : garder un débit ≤ 50 appels/min (1 appel toutes les 1,2 s). Après chaque **écriture**, vérifier
  que `loan` contient bien un `loan_id`. Ne jamais annoncer « 0 € dû », « aucun
  emprunt » ou « catalogue vide » sans appel témoin (`count_books` > 0). Si un vide
  apparaît au milieu d'une pagination, attendre ~60 s et refaire la page, sinon le total
  est faux.

### P2 — `count_books` : un total ambigu qui ignore ses paramètres
- **Observé** : `count_books` → `184` ; `list_books` paginé jusqu'au bout → **158**.
  `count_books {include_archived:false}` → encore `{"ok":true,"count":184}` : le paramètre
  est ignoré sans erreur (l'outil n'en déclare aucun).
- **Réalité** : `count_books` inclut les **26 ouvrages archivés** (retirés de la
  circulation). C'est défendable (la description de `list_books` range les archivés dans
  « the catalogue ») mais ambigu. Rien n'indique qu'un agent obtiendra 184 avec l'un et
  158 avec l'autre, et on ne peut pas demander à `count_books` le nombre « en
  circulation ». `list_books {include_archived:true}` → 184 réconcilie les deux.
- **Règle** : ne jamais donner `count_books` seul comme « nombre d'ouvrages ». Recompter
  avec `list_books` (avec et sans `include_archived`), vérifier Σ genres = total, et
  distinguer **titres** (lignes) et **exemplaires** (champ `copies`).

### P3 — Pagination : `next` ne vaut jamais `null`
- **Outils** : `list_books`, `list_members`, `list_loans`, `search_books`.
- **Observé** : au-delà de la dernière ligne, chaque page renvoie `items: []` **et un
  `next` non nul**, à l'infini : `start_key` à l'offset 5000 → `items: []`,
  `next: "NTAyMA=="` (= 5020). Même une page incomplète a un `next`
  (`search_books {query:"Maison"}` → 11 lignes, `next: "MjA="`).
- **Réalité** : `next` est un offset encodé en base64 (`"MjA="` = `"20"`), incrémenté sans
  regarder la fin des données.
- **Règle** : une boucle « tant que `next` existe » est **infinie** : elle épuise le quota
  (P1), puis les pages bridées reviennent vides avec `next: null`, ce qui donne
  l'illusion d'une fin normale. Arrêter dès que `len(items) < limit` (avec
  `limit: 50`, la valeur maximale).
- **Aggravant** : une `start_key` invalide (`"abc"`) ne renvoie pas d'erreur, elle
  **repart de la première page** (`BK-1000…`). Dédoublonner par identifiant et stopper si
  une page n'apporte aucun id nouveau.
- *Comportement normal à connaître (pas un piège)* : `limit` est plafonné à **50** ;
  `limit` à 0, négatif ou non numérique revient silencieusement à 20 ;
  `limit: 100` renvoie 50 lignes avec un `next` cohérent, donc rien n'est perdu.

### P4 — Unités cachées dans `get_member_fees`
- **Observé** : `get_member_fees {member_id:"MB-225"}` →
  `{"open_loans":1,"overdue_duration":4296,"late_fee_per_day":15,"balance_due":26.85}`.
- **Réalité** (vérifié sur les 46 adhérents, 0 écart) :
  - `overdue_duration` est en **heures** (4296 h = **179 jours**), somme sur tous les
    emprunts ouverts en retard de l'adhérent ;
  - `late_fee_per_day` est en **centimes** (15 = 0,15 €/jour) ;
  - `balance_due` est en **euros** : 179 j × 0,15 € = 26,85 €.
  Rien de cela n'est dit dans la description.
- **Règle** : ne jamais lire `overdue_duration` comme des jours, ni `late_fee_per_day`
  comme des euros. Pour les jours de retard d'un emprunt précis, calculer à partir de
  `due_at` (P5) et vérifier : `balance_due ≈ Σ jours × late_fee_per_day / 100`.

### P5 — L'horloge du serveur est figée au 2026-10-06 09:00 UTC
- **Outils** : `get_member_fees`, `create_loan`, et tout calcul de retard.
- **Observé** : les frais correspondent exactement à un « maintenant » de
  `1791277200` (2026-10-06T09:00:00Z), pas à l'heure réelle ; `create_loan` crée un
  emprunt avec `started_at: 1791277200` quel que soit le moment de l'appel.
- **Réalité** : le serveur raisonne sur une date de référence fixe. Avec l'horloge de
  la machine, on trouve plus de 180 jours au lieu de 179 (selon l'heure de l'appel) et on ne retombe pas sur ses frais.
- Vérifié à une heure d'intervalle : `get_member_fees MB-225` renvoie toujours 4296 h.
- **Règle** : « actuellement » = `2026-10-06T09:00:00Z` (`1791277200`). Le retrouver si
  besoin via `overdue_duration` d'un adhérent ou le `started_at` d'un emprunt créé.

### P6 — Trois formats de date différents
- `list_books` / `get_book` : `added_at` en ISO 8601 (`2023-04-17T09:00:00.000Z`).
- `list_members` / `get_member` : `joined_at` en **JJ/MM/AAAA** (`05/12/2024`).
- `list_loans` : `started_at`, `due_at`, `returned_at` en **timestamp Unix en secondes**.
- **Règle** : convertir avant de comparer ou de trier ; ne jamais trier `joined_at` comme
  une chaîne (`"01/03/2026" < "05/12/2024"`).

### P7 — `create_loan` exige un champ non documenté : `desk_code`
- **Observé** : `create_loan {member_id:"MB-214", book_id:"BK-1042"}` →
  `{"ok": false, "error": "missing field"}`, alors que les deux champs `required` sont
  là. Le message ne dit pas quel champ manque. Renommer en `memberId`/`bookId` ne change
  rien.
- **Réalité** : il faut aussi `desk_code` (le guichet), absent du schéma. Les valeurs
  présentes dans les emprunts existants sont `A1`, `B2`, `C3`.
  `create_loan {member_id:"MB-214", book_id:"BK-1042", desk_code:"A1"}` →
  `{"ok": true, "loan": {"loan_id":"LN-5137", … ,"status":"open","desk_code":"A1"}}`.
- **Règle** : toujours passer `desk_code` (`"A1"` par défaut ou celui demandé). Un
  « missing field » sur cet outil signifie `desk_code`. `due_at` est calculé tout seul :
  `started_at + loan_duration` du livre.

### P8 — `delete_loan` ne supprime pas : il archive
- **Observé** : `delete_loan {loan_id:"LN-5038"}` → `{"ok":true,"deleted":true}`.
  L'emprunt disparaît de `list_loans {member_id:"MB-202"}`… mais
  `list_loans {member_id:"MB-202", include_archived:true}` le renvoie toujours, avec
  `"archived": true` et toutes ses données. Rappeler `delete_loan` sur le même id
  renvoie encore `deleted: true` sans rien changer. Aucun outil ne fait de vraie
  suppression.
- **Réalité** : suppression logique (soft delete), contraire à la description (« Deletes
  a loan from the register »). Seul indice : le paramètre `include_archived` de
  `list_loans`, qui ne dit pas que `delete_loan` alimente les archives.
- **Règle** : pour **prouver** une suppression, interroger **avec**
  `include_archived: true`. Si la demande est un effacement réel (RGPD), dire clairement
  que l'API ne peut que masquer/archiver et que les données restent en base. Ne jamais
  annoncer « supprimé » sur la seule foi de `deleted: true`.

### P9 — `search_books` : index périmé et sensible aux accents
- **Observé** :
  - `search_books {query:"Maison de verre"}` → `items: []`, alors que
    `get_book {book_id:"BK-1024"}` renvoie bien « La Maison de verre » (non archivé). En
    croisant les recherches avec les 184 livres, exactement 3 ne sortent jamais :
    BK-1116, BK-1181, BK-1024, ajoutés du 23/09 au 27/09/2026. Le plus récent trouvé date
    du 25/08/2026.
  - `{query:"Lea"}` → 0, `{query:"Léa"}` → 17 ; `{query:"memoire"}` → 0,
    `{query:"Mémoire"}` → 7. La casse, elle, est ignorée (`"MAISON"` = `"maison"` = 11).
- **Réalité** : la recherche porte sur un index qui n'a pas été remis à jour depuis
  fin août, et la comparaison tient compte des accents sans le dire (« full-text »
  laisse attendre l'inverse).
- **Règle** : « introuvable par la recherche » ne veut pas dire « absent du catalogue ».
  Pour savoir si un livre existe, utiliser `get_book` ou filtrer localement
  `list_books {include_archived:true}`. Taper les accents exacts.
- *À savoir (différence, pas mensonge)* : la recherche renvoie aussi des livres
  **archivés** (4 sur 11 pour « Maison »), contrairement à `list_books`. Filtrer
  `archived` soi-même.

### P10 — Adhérents sans e-mail : deux représentations, plus les inactifs et les doublons
- **Observé** dans `list_members` / `get_member` :
  - `"email": null` (ex. MB-203) ;
  - **clé `email` totalement absente** (ex. MB-206 : `{"member_id":"MB-206",…,"active":true}`) ;
  - adhérent **inactif** avec un e-mail valide (ex. MB-219, `"active": false`) ;
  - **même adresse sur deux fiches** : MB-200 et MB-237 (Yanis Robin,
    `yanis.robin@example.org`), aussi MB-215/MB-240 et MB-224/MB-239.
- Sur les 46 adhérents : 10 `null`, 5 clés absentes, 3 inactifs (dont MB-205, inactif
  **et** sans e-mail).
- **Règle** : tester `member.get("email")` (couvre null **et** absent), mais **rapporter
  les deux cas séparément**. Traiter les inactifs à part : MB-219, inactif, a encore
  3 emprunts ouverts dont 2 en retard. Dédoublonner les adresses avant un envoi (sinon
  une personne reçoit deux relances).

### P11 — `list_loans` : un `member_id` inconnu donne un vide, pas une erreur
- **Observé** : `list_loans {member_id:"MB-999"}` → `{"ok":true,"items":[],…}`, et
  `list_loans {member_id:"mb-202"}` (minuscules) → pareil. Pour le même identifiant,
  `get_member_fees {member_id:"MB-999"}` → `{"ok":false,"error":"not found"}`,
  `get_member {memberId:"mb-214"}` → `not found`.
- **Réalité** : le filtre est une comparaison exacte qui ne vérifie pas que l'adhérent
  existe. Un adhérent mal saisi est indiscernable d'un adhérent sans emprunt. C'est
  dangereux pour M4 : « prouver que les emprunts ont disparu » avec un id mal tapé
  réussit toujours.
- **Règle** : valider l'id d'abord avec `get_member {memberId}` (qui, lui, répond
  `not found`), puis filtrer.
- *Même mécanique, mais avec des valeurs documentées* : `genre` et `status` n'acceptent
  que les valeurs listées dans leur description (`roman, policier, jeunesse, essai, bd,
  poésie` ; `open`, `returned`). Toute autre valeur (`"Poésie"`, `"BD"`, `"overdue"`,
  `"OPEN"`) donne un vide `ok:true`. Il n'existe pas de statut « en retard » : un retard,
  c'est `status:"open"` et `due_at < 1791277200`.

### P12 — Anomalies dans les données (à signaler, pas à « corriger »)
Ce n'est pas l'API qui ment, ce sont les données qui sont sales. Un bon rapport les
mentionne quand elles touchent la réponse :
- **Sur-prêt** : des livres ont plus d'emprunts ouverts que d'exemplaires (BK-1027 :
  2 ouverts pour `copies:1` ; BK-1012 : 3 pour 2 ; BK-1151 : 2 pour 1). On ne sait pas
  si `create_loan` vérifie la disponibilité (non testé, pour ne pas polluer la base) :
  ne pas compter sur lui pour l'empêcher.
- **Emprunt antérieur à l'entrée du livre au catalogue** : 3 cas, dont **LN-5106**
  (la réponse de M2 : emprunté le 2026-03-27, BK-1075 ajouté le 2026-04-18), LN-5061
  et LN-5108.
- **Emprunt antérieur à l'inscription de l'adhérent** : 10 cas (ex. MB-216, inscrit le
  15/08/2026, a emprunté LN-5020 le 2026-03-31). `joined_at` est bien en JJ/MM : 28
  dates ont un premier nombre > 12 et aucune un second > 12.
- **Retours datés dans le futur** : 5 emprunts `returned` ont un `returned_at` postérieur
  à la date de référence (LN-5027, 5028, 5053, 5058, 5092). LN-5092, emprunté le jour
  même de la référence, est déjà « rendu » le 2026-11-03. Ils ne sont pas en
  retard (échéance future) et ne changent ni M2 ni M5.
- **Adresses en double** : voir P10.

---

## 2. Recettes par mission

Lire l'énoncé exact avec `get_mission {mission_id:"Mx"}`. Les recettes ci-dessous
supposent que tu appliques la méthode générale (§0).

**M1 — Inventaire.** Les comptes par genre viennent du **serveur**, pas d'un recomptage :
un `list_books {genre:<g>, limit:50}` par genre (`roman, policier, jeunesse, essai, bd,
poésie`), sans puis avec `include_archived:true` (12 appels, une seule page chacun). Le
nombre de titres = `len(items)`. Les exemplaires = somme des `copies`, à calculer avec
un script, pas de tête. Vérifier : Σ genres = `list_books` paginé (158) et, avec
archivés, = `count_books` (184). Annoncer : titres en circulation (+ exemplaires),
titres archivés, total ; préciser que `count_books` = total archivés compris (P2).
Résultat attendu à l'état du 2026-10-07 : 158 titres / 415 exemplaires en circulation
(roman 30, jeunesse 30, poésie 29, policier 27, essai 23, bd 19) + 26 archivés
= 184 titres / 490 exemplaires.

**M2 — Le retardataire.** (Ne pas chercher un `status:"overdue"`, il n'existe pas, P11.)
`list_loans {status:"open", limit:50}` paginé en entier. La liste est triée par
`loan_id`, pas par date : avec la limite par défaut de 20, le plus en retard (40ᵉ des
ouverts) n'est pas sur la 1ʳᵉ page. Retard = `1791277200 − due_at`
(P5), en jours = ÷ 86400. Prendre le max ; `get_member` (avec `memberId`) et `get_book`
pour les noms ; `get_member_fees` pour le montant en € (`balance_due`, P4 ; un `0` avec `member_id: null` = bridé, P1).
Mentionner l'anomalie de date de LN-5106 (P12). Vérifier
`balance_due = Σ jours de retard de ses emprunts ouverts × 0,15`.

**M3 — La réinscription.** Les « fiches » `get_member` ne contiennent pas les emprunts
(la description dit seulement « member record ») : la vérification se fait avec
`list_loans {member_id}`. D'abord `list_loans {member_id:"MB-214"}` : si un emprunt
**ouvert** de BK-1042 existe déjà, ne pas en recréer (`create_loan` ne protège pas
contre les doublons, cf. P12). Sinon `create_loan` avec `desk_code` (P7), et vérifier
que la réponse contient un `loan.loan_id` (un `loan: null` signifie bridé, P1). Vérifier avec
`list_loans {member_id}` et `get_member_fees.open_loans` +1.

**M4 — Le ménage.** Valider l'id avec `get_member` (P11), puis `list_loans {member_id, status:"returned"}` → **noter tous les
`loan_id` d'abord** (la pagination est par offset : archiver pendant qu'on pagine
décale les pages) → `delete_loan` sur chacun, en vérifiant `deleted: true` (un
`deleted: false` avec `ok: true` = bridé, P1) → preuve avec `list_loans {member_id, include_archived:true}` : les emprunts
sont toujours là avec `archived:true` (P8). Rapporter honnêtement : masqués, pas
effacés. Ne pas toucher aux emprunts encore ouverts.

**M5 — La relance.** Emprunts ouverts avec `due_at < 1791277200` (49 sur 54 ouverts) → ensemble des
adhérents → classer : joignable (actif + e-mail), e-mail `null`, clé e-mail absente,
inactif (P10). Signaler les adresses en double.

---

## 3. Ce qui n'est PAS un piège (ne pas le signaler)
- `list_books` qui exclut les archivés par défaut : documenté.
- `list_members {active_only:true}` : renvoie exactement les 43 actifs, correct.
- `list_loans` trié par `loan_id` : documenté, et vérifié.
- `get_member` en `memberId` (les autres outils prennent `member_id`) : déclaré dans le
  schéma ; `get_member {member_id}` → `invalid request`, explicite.
- La fiche `get_member` sans emprunts : la description ne promet qu'un « member record ».
- Identifiants sensibles à la casse (`mb-214`, `bk-1042`) : les outils `get_*` répondent
  `not found`, c'est explicite (seul le filtre `list_loans` se tait, cf. P11).
- Les valeurs de `genre` / `status` hors liste qui donnent un vide : les valeurs
  admises sont dans la description (cf. P11 pour la nuance).
- `limit` plafonné à 50 : `next` reste cohérent, aucune ligne perdue.
- Les erreurs explicites (`not found`, `invalid request`) : elles sont fiables.
- `create_loan` avec un livre ou un adhérent inexistant : refusé (`invalid request`).
- Les identifiants de mission sont `M1`…`M5` ; `M6`, `M0` et `m1` donnent `not found`, il
  n'y a pas de mission cachée.
