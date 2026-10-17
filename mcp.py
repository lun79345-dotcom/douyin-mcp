#!/usr/bin/env python3
"""Tiny CLI client. Usage: python3 mcp.py <tool> '<json args>'   |   python3 mcp.py --list
Server URL: $DOUYIN_MCP_URL (default http://localhost:$DOUYIN_MCP_PORT/mcp, port 18070)."""
import json,os,sys,urllib.request
U=os.environ.get('DOUYIN_MCP_URL','http://localhost:%s/mcp'%os.environ.get('DOUYIN_MCP_PORT','18070'))
NP=urllib.request.build_opener(urllib.request.ProxyHandler({}))  # bypass system proxy for localhost
H={'Content-Type':'application/json','Accept':'application/json, text/event-stream'}
def post(body,sid=None,t=960):
    h=dict(H)
    if sid:h['Mcp-Session-Id']=sid
    r=NP.open(urllib.request.Request(U,json.dumps(body).encode(),h),timeout=t)
    return r.headers.get('Mcp-Session-Id'),r.read().decode()
def parse(out):
    for line in out.splitlines():
        line=line[5:].strip() if line.startswith('data:') else line.strip()
        if line.startswith('{'):return json.loads(line)
    return {}
sid,_=post({"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"cli","version":"1"}}})
post({"jsonrpc":"2.0","method":"notifications/initialized"},sid)
if len(sys.argv)<2 or sys.argv[1]=='--list':
    d=parse(post({"jsonrpc":"2.0","id":2,"method":"tools/list"},sid)[1])
    for t in d['result']['tools']:print(t['name'],'-',t.get('description','').split('\n')[0])
    sys.exit(0)
_,out=post({"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":sys.argv[1],"arguments":json.loads(sys.argv[2] if len(sys.argv)>2 else '{}')}},sid)
d=parse(out)
print(d['result']['content'][0]['text'] if 'result' in d and d['result'].get('content') else out)
