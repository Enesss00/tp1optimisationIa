#!/usr/bin/env python3
"""Calculs déterministes sur le serveur MCP bibliotheque-municipale (LECTURE SEULE).

Un modèle de langage recompte mal des dizaines de lignes JSON : ce script fait les
comptes à sa place, en appliquant toutes les règles du skill (débit, pagination,
bridage, horloge figée, unités). Il n'appelle jamais create_loan ni delete_loan.

    python3 biblio.py inventaire              # M1
    python3 biblio.py retards [N]             # M2 (N premiers retards, 5 par défaut)
    python3 biblio.py relance                 # M5
    python3 biblio.py emprunts MB-202         # M3/M4 : emprunts d'un adhérent, archivés compris
    python3 biblio.py appel get_book '{"book_id":"BK-1042"}'   # appel brut

Variables d'environnement requises : BIBLIO_MCP_URL, BIBLIO_TOKEN.
"""
import collections, datetime, json, os, sys, time, urllib.request

URL, TOK = os.environ.get("BIBLIO_MCP_URL"), os.environ.get("BIBLIO_TOKEN")
REF = 1791277200                     # « maintenant » du serveur : 2026-10-06T09:00:00Z (P5)
GENRES = ["roman", "policier", "jeunesse", "essai", "bd", "poésie"]
_sid, _last = None, [0.0]


def _post(body):
    h = {"Authorization": "Bearer " + TOK, "Content-Type": "application/json",
         "Accept": "application/json, text/event-stream"}
    if _sid:
        h["Mcp-Session-Id"] = _sid
    r = urllib.request.urlopen(urllib.request.Request(URL, json.dumps(body).encode(), h))
    txt = r.read().decode()
    data = [json.loads(l[5:]) for l in txt.splitlines() if l.startswith("data:")]
    return (data[-1] if data else (json.loads(txt) if txt.strip() else None)), r.headers.get("Mcp-Session-Id")


def call(tool, args=None):
    """Appel throttlé (≤ 48/min, P1) ; un `ok:true` à contenu null/vide suspect = bridage → pause et nouvel essai."""
    global _sid
    if not _sid:
        _, _sid = _post({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {
            "protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "biblio", "version": "1"}}})
        _post({"jsonrpc": "2.0", "method": "notifications/initialized"})
    for _ in range(3):
        w = 1.25 - (time.time() - _last[0])
        if w > 0:
            time.sleep(w)
        _last[0] = time.time()
        res = _post({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                     "params": {"name": tool, "arguments": args or {}}})[0]["result"]
        out = json.loads(res["content"][0]["text"])
        throttled = out.get("ok") and any(out.get(k, 1) is None for k in ("book", "member", "mission", "loan", "member_id"))
        if tool == "count_books" and out.get("count") == 0:
            throttled = True
        if not throttled:
            return out
        print(f"[bridage détecté sur {tool} : pause 65 s]", file=sys.stderr)
        time.sleep(65)
    sys.exit("Serveur toujours bridé : réessayer plus tard.")


def paginate(tool, args=None):
    """`next` n'est jamais null (P3) : arrêt sur page incomplète, dédoublonnage par contenu."""
    out, seen, key = [], set(), None
    while True:
        a = dict(args or {}, limit=50)
        if key:
            a["start_key"] = key
        r = call(tool, a)
        new = [i for i in r["items"] if json.dumps(i, sort_keys=True) not in seen]
        seen.update(json.dumps(i, sort_keys=True) for i in new)
        out += new
        if len(r["items"]) < 50 or not new:
            return out
        key = r["next"]


def day(ts):
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%d")


def inventaire():
    if call("count_books")["count"] == 0:
        sys.exit("count_books = 0 : bridé")
    circ = {g: call("list_books", {"genre": g, "limit": 50})["items"] for g in GENRES}
    tous = {g: call("list_books", {"genre": g, "include_archived": True, "limit": 50})["items"] for g in GENRES}
    total_list = paginate("list_books")
    count = call("count_books")["count"]
    print(f"{'genre':10} {'titres circ.':>12} {'archivés':>9} {'total':>6} {'ex. circ.':>10} {'ex. total':>10}")
    for g in GENRES:
        n, t = len(circ[g]), len(tous[g])
        print(f"{g:10} {n:12} {t - n:9} {t:6} {sum(b['copies'] for b in circ[g]):10} {sum(b['copies'] for b in tous[g]):10}")
    N, T = sum(map(len, circ.values())), sum(map(len, tous.values()))
    print(f"{'TOTAL':10} {N:12} {T - N:9} {T:6} {sum(b['copies'] for v in circ.values() for b in v):10} "
          f"{sum(b['copies'] for v in tous.values() for b in v):10}")
    print(f"\nContrôles : Σ genres en circulation = {N} ; list_books paginé = {len(total_list)} "
          f"({'OK' if N == len(total_list) else 'ÉCART'}) ; Σ genres avec archivés = {T} ; "
          f"count_books = {count} ({'OK' if T == count else 'ÉCART'}, count_books inclut les archivés).")


def retards(n=5):
    ouverts = paginate("list_loans", {"status": "open"})
    late = sorted((l for l in ouverts if l["due_at"] < REF), key=lambda l: l["due_at"])
    print(f"Référence serveur : 2026-10-06T09:00Z ; {len(ouverts)} emprunts ouverts, {len(late)} en retard.\n")
    for l in late[:n]:
        print(f"{l['loan_id']}  {l['member_id']}  {l['book_id']}  échéance {day(l['due_at'])}  "
              f"retard {(REF - l['due_at']) / 86400:g} j")
    w = late[0]
    m, b = call("get_member", {"memberId": w["member_id"]})["member"], call("get_book", {"book_id": w["book_id"]})["book"]
    f = call("get_member_fees", {"member_id": w["member_id"]})
    jours = sum((REF - l["due_at"]) / 86400 for l in late if l["member_id"] == w["member_id"])
    print(f"\nPlus en retard : {w['loan_id']} — {m['member_id']} {m['first_name']} {m['last_name']} — "
          f"{b['book_id']} « {b['title']} » ({b['author']}, ajouté le {b['added_at'][:10]}) — emprunté le "
          f"{day(w['started_at'])} — {(REF - w['due_at']) / 86400:g} jours de retard")
    print(f"get_member_fees brut : {json.dumps(f)}")
    print(f"→ overdue_duration = {f['overdue_duration']} HEURES = {f['overdue_duration'] / 24:g} j ; "
          f"late_fee_per_day = {f['late_fee_per_day']} CENTIMES ; balance_due = {f['balance_due']} € "
          f"(contrôle : {jours:g} j × {f['late_fee_per_day'] / 100:.2f} € = {jours * f['late_fee_per_day'] / 100:.2f} €)")
    if w["started_at"] < datetime.datetime.fromisoformat(b["added_at"].replace("Z", "+00:00")).timestamp():
        print("⚠ anomalie de données : emprunt antérieur à l'entrée du livre au catalogue (à signaler).")


def relance():
    ouverts = paginate("list_loans", {"status": "open"})
    late = [l for l in ouverts if l["due_at"] < REF]
    M = {m["member_id"]: m for m in paginate("list_members")}
    qui = sorted({l["member_id"] for l in late})
    cas = collections.defaultdict(list)
    for mid in qui:
        m = M[mid]
        if not m["active"]:
            cas["inactif" + (" (avec e-mail)" if m.get("email") else " (sans e-mail)")].append(mid)
        elif "email" not in m:
            cas["clé email absente"].append(mid)
        elif m["email"] is None:
            cas["email null"].append(mid)
        else:
            cas["joignable"].append(mid)
    print(f"{len(late)} emprunts en retard → {len(qui)} adhérents.\n")
    for k in ["joignable", "email null", "clé email absente", "inactif (avec e-mail)", "inactif (sans e-mail)"]:
        if cas[k]:
            print(f"{k} ({len(cas[k])}) :")
            for mid in cas[k]:
                m = M[mid]
                print(f"   {mid} {m['first_name']} {m['last_name']} {m.get('email', '<clé absente>')} "
                      f"— {sum(l['member_id'] == mid for l in late)} retard(s)")
    adr = collections.defaultdict(list)
    for mid in cas["joignable"]:
        adr[M[mid]["email"]].append(mid)
    dup = {a: v for a, v in adr.items() if len(v) > 1}
    print(f"\nAdresses distinctes à contacter : {len(adr)}" + (f" ; doublons : {dup}" if dup else ""))


def emprunts(mid):
    if not call("get_member", {"memberId": mid}).get("ok"):
        sys.exit(f"{mid} : not found (vérifier l'identifiant, P11)")
    for arch in (False, True):
        rows = paginate("list_loans", {"member_id": mid, "include_archived": arch})
        print(f"list_loans {{member_id:{mid}, include_archived:{str(arch).lower()}}} → {len(rows)} ligne(s)")
        for l in rows:
            print(f"   {l['loan_id']} {l['book_id']} {l['status']:8} archived={l['archived']} "
                  f"due {day(l['due_at'])}" + (f" rendu {day(l['returned_at'])}" if l["returned_at"] else ""))


if __name__ == "__main__":
    if not URL or not TOK:
        sys.exit("Définir BIBLIO_MCP_URL et BIBLIO_TOKEN.")
    cmd, args = (sys.argv[1] if len(sys.argv) > 1 else ""), sys.argv[2:]
    if cmd == "inventaire":
        inventaire()
    elif cmd == "retards":
        retards(int(args[0]) if args else 5)
    elif cmd == "relance":
        relance()
    elif cmd == "emprunts" and args:
        emprunts(args[0])
    elif cmd == "appel" and args:
        print(json.dumps(call(args[0], json.loads(args[1]) if len(args) > 1 else {}), ensure_ascii=False, indent=2))
    else:
        sys.exit(__doc__)
