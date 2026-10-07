import json,sys,time
from mcp import call
LOG="calls.jsonl"; _last=[0.0]
def raw(name,args):
    w=1.15-(time.time()-_last[0])
    if w>0: time.sleep(w)
    _last[0]=time.time()
    r=call("tools/call",{"name":name,"arguments":args})["result"]
    txt=r["content"][0]["text"]
    with open(LOG,"a") as f: f.write(json.dumps({"t":time.strftime("%T"),"tool":name,"args":args,"raw":txt,"isError":r.get("isError")},ensure_ascii=False)+"\n")
    try: return json.loads(txt)
    except Exception: return {"_text":txt,"isError":r.get("isError")}
def pg(name,args,limit=None):
    out=[];k=None;pages=[]
    while True:
        a=dict(args)
        if limit: a["limit"]=limit
        if k: a["start_key"]=k
        r=raw(name,a); out+=r.get("items",[]); pages.append((len(r.get("items",[])),r.get("next")))
        k=r.get("next")
        if not k or (len(pages)>1 and pages[-1][0]==0 and pages[-2][0]==0): break
    return out,pages
