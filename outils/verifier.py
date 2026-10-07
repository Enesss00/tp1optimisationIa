#!/usr/bin/env python3
"""Rejoue, en LECTURE SEULE, les preuves des pièges du skill et les réponses des missions.

Usage :
    set -a; source .env; set +a        # BIBLIO_MCP_URL et BIBLIO_TOKEN
    python3 outils/verifier.py           # ~35 appels, ~45 s
    python3 outils/verifier.py --bridage # + démonstration de P1 (bloque le token ~1 min)

Aucun appel à create_loan / delete_loan, sauf pendant --bridage où le serveur les
ignore (c'est justement ce que la démonstration montre). Dépendances : aucune.
"""
import base64, collections, json, os, sys, time, urllib.request

URL = os.environ.get("BIBLIO_MCP_URL")
TOK = os.environ.get("BIBLIO_TOKEN")
if not URL or not TOK:
    sys.exit("Définir BIBLIO_MCP_URL et BIBLIO_TOKEN (voir .env.example).")

REF = 1791277200  # 2026-10-06T09:00:00Z, « maintenant » du serveur (P5)
PAUSE = 1.25      # ≤ 48 appels/min : sous la limite de 60/min (P1)
_sid, _last, _n = None, [0.0], [0]


def _post(body):
    h = {"Authorization": "Bearer " + TOK, "Content-Type": "application/json",
         "Accept": "application/json, text/event-stream"}
    if _sid:
        h["Mcp-Session-Id"] = _sid
    r = urllib.request.urlopen(urllib.request.Request(URL, json.dumps(body).encode(), h))
    txt, sid = r.read().decode(), r.headers.get("Mcp-Session-Id")
    data = [json.loads(l[5:]) for l in txt.splitlines() if l.startswith("data:")]
    return (data[-1] if data else (json.loads(txt) if txt.strip() else None)), sid


def _init():
    global _sid
    _, _sid = _post({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {
        "protocolVersion": "2025-03-26", "capabilities": {},
        "clientInfo": {"name": "verifier", "version": "1"}}})
    _post({"jsonrpc": "2.0", "method": "notifications/initialized"})


def rpc(method, params, throttle=True):
    if throttle:
        w = PAUSE - (time.time() - _last[0])
        if w > 0:
            time.sleep(w)
    _last[0] = time.time(); _n[0] += 1
    return _post({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})[0]


def call(tool, args=None, throttle=True):
    res = rpc("tools/call", {"name": tool, "arguments": args or {}}, throttle)["result"]
    return json.loads(res["content"][0]["text"])


def paginate(tool, args=None):
    """Arrêt quand la page est incomplète : `next` n'est jamais null (P3)."""
    out, key = [], None
    while True:
        a = dict(args or {}, limit=50)
        if key:
            a["start_key"] = key
        r = call(tool, a)
        out += r["items"]
        if len(r["items"]) < 50:
            return out
        key = r["next"]


RESULTS = []


def check(code, label, ok, detail):
    RESULTS.append(ok)
    print(f"[{'OK ' if ok else 'ÉCHEC'}] {code:4} {label}\n        {detail}")


def canary():
    c = call("count_books")["count"]
    if c == 0:
        sys.exit("count_books = 0 : token bridé (P1). Attendre 60 s et relancer.")
    return c


def main():
    _init()
    print(f"Serveur : {URL}\n")
    tools = {t["name"]: t for t in rpc("tools/list", {})["result"]["tools"]}
    count = canary()

    # --- livres
    books = paginate("list_books")
    books_all = paginate("list_books", {"include_archived": True})
    arch = [b for b in books_all if b["archived"]]
    check("P2", "count_books inclut les archivés, list_books non",
          count == len(books_all) and len(books) == len(books_all) - len(arch),
          f"count_books={count} ; list_books={len(books)} ; avec archivés={len(books_all)} ({len(arch)} archivés)")
    c2 = call("count_books", {"include_archived": False})["count"]
    check("P2", "count_books ignore include_archived:false", c2 == count, f"count_books{{include_archived:false}} = {c2}")

    r = call("list_books", {"start_key": base64.b64encode(b"5000").decode()})
    check("P3", "next jamais null, même au-delà des données",
          r["items"] == [] and r["next"] is not None,
          f"offset 5000 → items={r['items']} next={r['next']!r} ({base64.b64decode(r['next']).decode()})")
    r = call("list_books", {"start_key": "abc"})
    check("P3", "start_key invalide → retour silencieux à la page 1",
          r["items"] and r["items"][0]["book_id"] == books[0]["book_id"],
          f"start_key='abc' → 1er livre {r['items'][0]['book_id']}")

    # --- emprunts, frais, horloge
    loans_all = paginate("list_loans", {"include_archived": True})
    loans = [l for l in loans_all if not l["archived"]]
    opened = [l for l in loans if l["status"] == "open"]
    late = sorted((l for l in opened if l["due_at"] < REF), key=lambda l: l["due_at"])
    worst = late[0]
    fees = call("get_member_fees", {"member_id": worst["member_id"]})
    days = sum((REF - l["due_at"]) / 86400 for l in late if l["member_id"] == worst["member_id"])
    check("P4/P5", "overdue_duration en heures, late_fee_per_day en centimes, horloge figée",
          fees["overdue_duration"] == days * 24 and abs(fees["balance_due"] - days * fees["late_fee_per_day"] / 100) < 0.005,
          f"{worst['member_id']} : {json.dumps(fees)} ; calcul avec REF=2026-10-06T09:00Z : {days:g} j = {days*24:g} h → {days*0.15:.2f} €")

    props = tools["create_loan"]["inputSchema"]["properties"]
    desks = collections.Counter(l["desk_code"] for l in loans_all)
    check("P7", "desk_code absent du schéma de create_loan mais présent sur chaque emprunt",
          "desk_code" not in props and None not in desks,
          f"schéma : {sorted(props)} ; desk_code observés : {dict(desks)}")

    archived = [l for l in loans_all if l["archived"]]
    check("P8", "un emprunt « supprimé » reste lisible avec include_archived",
          bool(archived),
          f"{len(loans)} visibles par défaut, {len(loans_all)} avec include_archived ; archivés : "
          + ", ".join(f"{l['loan_id']}({l['member_id']},{l['status']})" for l in archived))

    # --- recherche
    s1 = call("search_books", {"query": "Maison de verre"})["items"]
    g = call("get_book", {"book_id": "BK-1024"})["book"]
    check("P9", "index de recherche périmé", s1 == [] and g is not None,
          f"search 'Maison de verre' → {len(s1)} ; get_book BK-1024 → {g and g['title']} (ajouté {g and g['added_at'][:10]})")
    a, b = (len(call("search_books", {"query": q, "limit": 50})["items"]) for q in ("Lea", "Léa"))
    check("P9", "recherche sensible aux accents", a == 0 and b > 0, f"'Lea' → {a} ; 'Léa' → {b}")

    # --- adhérents
    members = paginate("list_members")
    M = {m["member_id"]: m for m in members}
    null = [m for m in members if "email" in m and m["email"] is None]
    absent = [m for m in members if "email" not in m]
    check("P10", "deux représentations de « pas d'e-mail »", bool(null) and bool(absent),
          f"email:null → {len(null)} ; clé absente → {len(absent)} ; inactifs → {sum(not m['active'] for m in members)}")

    e = call("list_loans", {"member_id": "MB-999"})
    f = call("get_member_fees", {"member_id": "MB-999"})
    check("P11", "list_loans : member_id inconnu → vide ok:true (au lieu de not found)",
          e["ok"] and e["items"] == [] and not f["ok"],
          f"list_loans MB-999 → {json.dumps(e)} ; get_member_fees MB-999 → {json.dumps(f)}")

    B = {b["book_id"]: b for b in books_all}
    over = [(k, n, B[k]["copies"]) for k, n in collections.Counter(l["book_id"] for l in opened).items() if n > B[k]["copies"]]
    check("P12", "anomalie : plus d'emprunts ouverts que d'exemplaires", bool(over),
          ", ".join(f"{k}: {n} ouverts / {c} ex." for k, n, c in over))

    # --- réponses des missions
    print("\n--- Missions (recalculées depuis le serveur) ---")
    genres = collections.Counter(b["genre"] for b in books)
    print(f"M1 : {len(books)} titres en circulation ({sum(b['copies'] for b in books)} ex.) + "
          f"{len(arch)} archivés = {len(books_all)} ({sum(b['copies'] for b in books_all)} ex.) ; {dict(genres)}")
    bk = B[worst["book_id"]]; mb = M[worst["member_id"]]
    print(f"M2 : {worst['loan_id']} — {mb['member_id']} {mb['first_name']} {mb['last_name']} — "
          f"{bk['book_id']} « {bk['title']} » — {(REF - worst['due_at']) / 86400:g} j — {fees['balance_due']} €")
    m3 = [l["loan_id"] for l in loans if l["member_id"] == "MB-214" and l["book_id"] == "BK-1042" and l["status"] == "open"]
    print(f"M3 : emprunt(s) ouvert(s) MB-214/BK-1042 : {m3 or 'aucun'}")
    m4 = [(l["loan_id"], l["status"], "archivé" if l["archived"] else "visible") for l in loans_all if l["member_id"] == "MB-202"]
    print(f"M4 : emprunts de MB-202 : {m4}")
    who = sorted({l["member_id"] for l in late})
    ok = [m for m in who if M[m]["active"] and M[m].get("email")]
    print(f"M5 : {len(who)} adhérents en retard ; joignables {len(ok)} ({len({M[m]['email'] for m in ok})} adresses) ; "
          f"email null {[m for m in who if 'email' in M[m] and M[m]['email'] is None]} ; "
          f"clé absente {[m for m in who if 'email' not in M[m]]} ; inactifs {[m for m in who if not M[m]['active']]}")

    if "--bridage" in sys.argv:
        print("\n--- P1 : rafale sans pause (le token sera bloqué ~1 min) ---")
        n = 0
        while call("count_books", throttle=False)["count"]:
            n += 1
        print(f"bridé au {n + 1}ᵉ appel de la rafale ; réponses pendant le bridage :")
        for t, a in [("get_member_fees", {"member_id": worst["member_id"]}), ("get_book", {"book_id": "BK-1042"}),
                     ("create_loan", {"member_id": "MB-214", "book_id": "BK-9999", "desk_code": "A1"}),
                     ("delete_loan", {"loan_id": "LN-9999"})]:
            print(f"  {t} {json.dumps(a)} → {json.dumps(call(t, a, throttle=False))}")
        RESULTS.append(True)

    print(f"\n{sum(RESULTS)}/{len(RESULTS)} vérifications OK — {_n[0]} appels.")
    return 0 if all(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
