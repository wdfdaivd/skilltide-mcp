#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MCP 服务器的真实协议自测 —— 起进程、走 stdio、逐条断言。

★ 为什么用【独立文件】而不是内联 heredoc:
   我连续两次在 rsh 里用嵌套 heredoc 跑 Python，输出被截断/混杂 ⇒ JSONDecodeError
   （不是服务器的问题，是我的测试方法的问题）。
   ⇒ 按今晚的规矩: 复杂脚本写文件再跑。
"""
import json
import subprocess
import sys

HERE = '/opt/dsh-app/mcp/skilltide-mcp'
PY = sys.executable


def call(reqs):
    inp = '\n'.join(json.dumps(r, ensure_ascii=False) for r in reqs) + '\n'
    p = subprocess.run([PY, 'skilltide_mcp.py'], input=inp, capture_output=True,
                       text=True, cwd=HERE)
    out = []
    for ln in (p.stdout or '').strip().split('\n'):
        if ln.strip():
            try:
                out.append(json.loads(ln))
            except Exception:
                print('  ★ 非 JSON 输出行:', ln[:160])
    return out, p.stderr or ''


def main():
    print(f'  启动命令: SKILLTIDE_DB=<db> {PY} {HERE}/skilltide_mcp.py  (stdio)')
    init = {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
            'params': {'protocolVersion': '2024-11-05', 'capabilities': {},
                       'clientInfo': {'name': 'selftest', 'version': '1'}}}
    reqs = [init,
            {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
            {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
            {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
             'params': {'name': 'search_tools',
                        'arguments': {'query': 'kubectl', 'limit': 5}}},
            {'jsonrpc': '2.0', 'id': 4, 'method': 'tools/call',
             'params': {'name': 'search_tools',
                        'arguments': {'query': '做 PPT', 'limit': 3}}},
            {'jsonrpc': '2.0', 'id': 5, 'method': 'tools/call',
             'params': {'name': 'list_categories'}},
            {'jsonrpc': '2.0', 'id': 6, 'method': 'tools/call',
             'params': {'name': 'get_tool',
                        'arguments': {'key': 'rohitg00-kubectl-mcp-server'}}},
            {'jsonrpc': '2.0', 'id': 7, 'method': 'tools/call',
             'params': {'name': 'nope', 'arguments': {}}},
            {'jsonrpc': '2.0', 'id': 8, 'method': 'ping'},
            ]
    out, err = call(reqs)
    if err.strip():
        print('  ★ STDERR:', err[:300])
    by = {d.get('id'): d for d in out}
    fails = []

    r = by.get(1, {}).get('result', {})
    print(f"  ① initialize → {r.get('serverInfo')} · protocol={r.get('protocolVersion')}")
    if r.get('protocolVersion') != '2024-11-05':
        fails.append('initialize')

    ts = [t['name'] for t in by.get(2, {}).get('result', {}).get('tools', [])]
    print(f"  ② tools/list → {ts}")
    if ts != ['search_tools', 'get_tool', 'list_categories']:
        fails.append('tools/list')

    if 3 in by:
        t = json.loads(by[3]['result']['content'][0]['text'])
        print(f"  ③ search_tools('kubectl') count={t['count']} isError={by[3]['result']['isError']}")
        for x in t['results']:
            print(f"       {x['name'][:40]:42} {x['url'][:52]}")
        names = ' '.join(x['name'] for x in t['results'])
        if 'kubectl-mcp-server' not in names:
            fails.append('search kubectl')

    if 4 in by:
        t = json.loads(by[4]['result']['content'][0]['text'])
        print(f"  ④ search_tools('做 PPT') count={t['count']}")
        for x in t['results'][:3]:
            print(f"       {x['name'][:24]:26} kind={x['kind']:10} cat={x.get('category')}")
        if t['count'] < 1:
            fails.append('search CJK')

    if 5 in by:
        t = json.loads(by[5]['result']['content'][0]['text'])
        print(f"  ⑤ list_categories → {len(t['ai_tool_categories'])} 类 · "
              f"{len(t['field_tags'])} 标签 · 目录 {t['catalogue_total']} · 工具 {t['ai_tool_total']}")
        if len(t['ai_tool_categories']) != 15:
            fails.append('categories')

    if 6 in by:
        t = json.loads(by[6]['result']['content'][0]['text'])
        print(f"  ⑥ get_tool → {t.get('name')} · fields={t.get('fields')} · "
              f"install={t.get('install_cmd')}")
        if not t.get('name'):
            fails.append('get_tool')

    if 7 in by:
        e = by[7].get('error', {})
        print(f"  ⑦ 未知 tool → error code={e.get('code')} msg={str(e.get('message'))[:40]}")
        if e.get('code') != -32602:
            fails.append('unknown tool handling')

    if 8 in by:
        print(f"  ⑧ ping → {by[8].get('result')}")
        if by[8].get('result') != {}:
            fails.append('ping')

    print()
    if fails:
        print('  ★★ 失败项:', fails)
        return 1
    print('  ★★ 全部 8 项通过（真实 stdio 协议，不是 import 测试）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
