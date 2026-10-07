import json, sys, os, urllib.request, ssl
URL=os.environ["BIBLIO_MCP_URL"]; TOK=os.environ["BIBLIO_TOKEN"]
SF=os.path.join(os.path.dirname(os.path.abspath(__file__)),"session.txt")
def post(body, sid=None):
    h={"Authorization":"Bearer "+TOK,"Content-Type":"application/json","Accept":"application/json, text/event-stream"}
    if sid: h["Mcp-Session-Id"]=sid
    r=urllib.request.urlopen(urllib.request.Request(URL,json.dumps(body).encode(),h))
    txt=r.read().decode(); s=r.headers.get("Mcp-Session-Id")
    out=None
    for line in txt.splitlines():
        if line.startswith("data:"): out=json.loads(line[5:])
    if out is None and txt.strip(): out=json.loads(txt)
    return out,s
def session():
    if os.path.exists(SF): return open(SF).read().strip()
    _,sid=post({"jsonrpc":"2.0","id":0,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"tp","version":"1"}}})
    post({"jsonrpc":"2.0","method":"notifications/initialized"},sid)
    open(SF,"w").write(sid); return sid
def call(method,params):
    sid=session()
    try: return post({"jsonrpc":"2.0","id":1,"method":method,"params":params},sid)[0]
    except urllib.error.HTTPError as e:
        os.remove(SF); sid=session(); return post({"jsonrpc":"2.0","id":1,"method":method,"params":params},sid)[0]
if __name__=="__main__":
    if sys.argv[1]=="list":
        print(json.dumps(call("tools/list",{}),ensure_ascii=False,indent=1))
    else:
        args=json.loads(sys.argv[2]) if len(sys.argv)>2 else {}
        res=call("tools/call",{"name":sys.argv[1],"arguments":args})
        if "result" in res:
            for c in res["result"].get("content",[]):
                print(c.get("text",c))
            if res["result"].get("isError"): print("[isError=true]")
        else: print(json.dumps(res,ensure_ascii=False))
