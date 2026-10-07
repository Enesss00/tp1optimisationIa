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

1. **Débit ≤ 1 appel/seconde**, et pas plus d'une cinquantaine d'appels par minute (voir P1).
2. **Pagination** : boucle sur `next` mais **arrête-toi à la première page vide** (voir P3).
   Prends `limit: 50` (le maximum effectif) pour économiser des appels.
3. **Avant de conclure qu'une liste est vide** (« aucun résultat », « livre introuvable »),
   fais un appel témoin : `count_books` doit renvoyer un nombre > 0. S'il renvoie 0,
   tu es bridé (P1) : attends ~60 s et recommence.
4. **Recoupe** : un total se vérifie par deux chemins (compteur vs liste paginée, somme
   par genre vs total, frais serveur vs calcul à partir des emprunts).
5. **Après toute écriture**, relis l'état avec `list_loans` *avec et sans*
   `include_archived: true`.

---

## 1. Pièges

### P1 — Limitation de débit silencieuse (TOUS les outils)
- **Observé** : après ~60 appels en moins d'une minute, toutes les lectures renvoient
  `{"ok": true, "items": [], "next": null}`, `count_books` → `{"ok": true, "count": 0}`,
  `get_book` → `{"ok": true, "book": null}`, même `list_missions` → `items: []`.
  Pas d'erreur, pas de code HTTP 429, pas d'en-tête de quota.
- **Réalité** : le serveur bride le token et maquille le refus en résultat vide valide.
  Ça revient tout seul au bout de 30 à 60 s environ.
- **Règle** : ne jamais interpréter un vide comme une donnée tant que l'appel témoin
  (`count_books` > 0) n'a pas confirmé que le serveur répond normalement. Espacer les
  appels (≥ 1,1 s). Si un vide apparaît au milieu d'une pagination, refaire la page
  après une pause, sinon le total est faux.

### P2 — `count_books` ne compte pas la même chose que `list_books`
- **Observé** : `count_books` → `184` ; `list_books` paginé jusqu'au bout → **158** livres.
- **Réalité** : `count_books` inclut les **26 ouvrages archivés** (retirés de la
  circulation). `list_books` les exclut par défaut — ça, c'est documenté dans sa
  description et ce n'est pas un bug. Le piège est que la description de `count_books`
  (« size of the catalogue ») ne le dit pas, et qu'il n'a aucun paramètre pour choisir.
  `list_books {include_archived: true}` → 184, ce qui réconcilie les deux.
- **Règle** : ne jamais donner `count_books` comme « nombre d'ouvrages » sans préciser
  qu'il inclut les archivés. Toujours recompter avec `list_books` (avec et sans
  `include_archived`) et vérifier que la somme par genre égale le total.
  Distinguer aussi **titres** (lignes) et **exemplaires** (champ `copies`).

### P3 — `next` n'est jamais `null` à la fin des données
- **Outils** : `list_books`, `list_members`, `list_loans`, `search_books`.
- **Observé** : la page qui suit la dernière ligne renvoie `items: []` **et un `next`
  non nul** ; ça continue sur plusieurs pages vides (ex. `list_books` défaut : pages
  vides à offset 160, 180, …, 340 avant que `next` passe à `null`).
- **Réalité** : `next` est un offset encodé en base64 (`"MjA="` = `"20"`) qui avance
  sans tenir compte de la fin des données.
- **Règle** : arrêter la pagination à la **première page vide** (ou dès que
  `len(items) < limit`, en vérifiant par un appel de plus). Une boucle « tant que `next`
  existe » gaspille ~10 appels par liste et déclenche P1, qui fausse alors le reste.
- *Comportement normal à connaître (pas un piège)* : `limit` est plafonné à **50** ;
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
  la machine, on trouve 180,1 jours au lieu de 179 et on ne retombe pas sur ses frais.
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
- **Réalité** : suppression logique (soft delete) contraire à la description (« Deletes
  a loan from the register »).
- **Règle** : pour **prouver** une suppression, interroger **avec**
  `include_archived: true`. Si la demande est un effacement réel (RGPD), dire clairement
  que l'API ne peut que masquer/archiver et que les données restent en base. Ne jamais
  annoncer « supprimé » sur la seule foi de `deleted: true`.

### P9 — `search_books` : index périmé, et il inclut les archivés
- **Observé** : `search_books {query:"Maison de verre"}` → `items: []`, alors que
  `get_book {book_id:"BK-1024"}` renvoie bien « La Maison de verre » (non archivé). En
  cherchant tous les noms d'auteurs, 3 livres ne sortent jamais : BK-1116, BK-1181,
  BK-1024, soit exactement les livres ajoutés après le 2026-08-25 (les plus récents).
  À l'inverse, la recherche renvoie des livres **archivés** (ex. 4 sur 11 pour
  « Maison »), contrairement à `list_books`.
- **Réalité** : la recherche porte sur un index qui n'a pas été remis à jour depuis le
  dernier mois et qui ne filtre pas l'archivage.
- **Règle** : « introuvable par la recherche » ne veut pas dire « absent du catalogue ».
  Pour savoir si un livre existe, utiliser `get_book` ou filtrer localement le résultat
  de `list_books {include_archived:true}`. Filtrer `archived` soi-même dans les
  résultats de recherche.

### P10 — Adhérents sans e-mail : deux représentations, plus les inactifs et les doublons
- **Observé** dans `list_members` / `get_member` :
  - `"email": null` (ex. MB-203) ;
  - **clé `email` totalement absente** (ex. MB-206 : `{"member_id":"MB-206",…,"active":true}`) ;
  - adhérent **inactif** avec un e-mail valide (ex. MB-219, `"active": false`) ;
  - **même adresse sur deux fiches** : MB-200 et MB-237 (Yanis Robin,
    `yanis.robin@example.org`), aussi MB-215/MB-240 et MB-224/MB-239.
- **Règle** : tester `member.get("email")` (couvre null **et** absent), mais **rapporter
  les deux cas séparément**. Traiter les inactifs à part. Dédoublonner les adresses avant
  un envoi (sinon une personne reçoit deux relances).

### P11 — Petites incohérences d'interface (pas des bugs, mais à connaître)
- `get_member` prend **`memberId`** (camelCase) ; tous les autres outils prennent
  `member_id`. C'est dans le schéma ; `member_id` sur `get_member` → `"invalid request"`.
- La « fiche » adhérent (`get_member`) **ne contient pas les emprunts** : pour vérifier
  un emprunt, utiliser `list_loans {member_id}` (et `get_member_fees` → `open_loans`).
- Les identifiants sont sensibles à la casse : `mb-214` → `not found`.

---

## 2. Recettes par mission

Lire l'énoncé exact avec `get_mission {mission_id:"Mx"}`. Les recettes ci-dessous
supposent que tu appliques la méthode générale (§0).

**M1 — Inventaire.** `list_books` paginé deux fois : sans puis avec
`include_archived:true`. Compter les titres par `genre`, sommer `copies`. Annoncer :
titres en circulation (+ exemplaires), titres archivés, total ; préciser que
`count_books` = total archivés compris (P2). Vérifier : Σ genres = total.

**M2 — Le retardataire.** `list_loans {status:"open", limit:50}` paginé en entier
(l'emprunt le plus en retard n'est pas dans la 1ʳᵉ page). Retard = `1791277200 − due_at`
(P5), en jours = ÷ 86400. Prendre le max ; `get_member` (avec `memberId`) et `get_book`
pour les noms ; `get_member_fees` pour le montant en € (`balance_due`, P4). Vérifier
`balance_due = Σ jours de retard de ses emprunts ouverts × 0,15`.

**M3 — La réinscription.** `create_loan` avec `desk_code` (P7). Vérifier avec
`list_loans {member_id}` (pas `get_member`, P11) et `get_member_fees.open_loans` +1.
Avant de recréer, vérifier qu'un emprunt ouvert identique n'existe pas déjà (ne pas
créer de doublon à chaque essai).

**M4 — Le ménage.** `list_loans {member_id, status:"returned"}` → `delete_loan` sur
chacun → preuve avec `list_loans {member_id, include_archived:true}` : les emprunts
sont toujours là avec `archived:true` (P8). Rapporter honnêtement : masqués, pas
effacés. Ne pas toucher aux emprunts encore ouverts.

**M5 — La relance.** Emprunts ouverts avec `due_at < 1791277200` → ensemble des
adhérents → classer : joignable (actif + e-mail), e-mail `null`, clé e-mail absente,
inactif (P10). Signaler les adresses en double.

---

## 3. Ce qui n'est PAS un piège (ne pas le signaler)
- `list_books` qui exclut les archivés par défaut : documenté.
- `list_members {active_only:true}` : renvoie exactement les 43 actifs, correct.
- `list_loans` trié par `loan_id` : documenté, et vérifié.
- `get_member` en `memberId` : déclaré dans le schéma de l'outil.
- `limit` plafonné à 50 : `next` reste cohérent, aucune ligne perdue.
- Les erreurs explicites (`not found`, `invalid request`) : elles sont fiables.
