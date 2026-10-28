#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""skilltide-mcp —— 用 MCP server 的形式暴露 Anclum 的目录，让 AI agent 能搜索。

★ 为什么做它（lead 查证的外链钥匙）:
   · awesome-mcp-servers 的 Scope 明文: 只收【有公开 GitHub 仓库、可安装运行的 MCP server】，
     不收网站 ⇒ 提交网站不成立。
   · 但它的 Aggregators 分类里已有先例: a2asearch-mcp / mcpqueen
     —— "Search a directory of MCP servers…" ⇒ ★ 以 MCP server 形式就能被收录。
   · ★ 而它的 CONTRIBUTING 明写: automated agent 加 🤖🤖🤖 到 PR 标题即可 opt-in，
     "Merging your PR will be fast-tracked" ⇒ 这个生态【明确欢迎 agent】。

★ 技术选择: 【零依赖】—— 只用 Python 标准库直接实现 MCP 的 JSON-RPC over stdio。
   理由（实测）: 服务器可用内存 1.2G，装 mcp 官方 SDK 会拉进 pydantic/anyio/httpx 等一批
   依赖；而这个 server 只需要 tools/list + tools/call 两个方法 ⇒ 自己实现更轻、更可控，
   也更容易被审阅（一个文件、无隐藏依赖）。
   ★ 这也让"别人 clone 下来就能跑"成为事实（无 pip install）。

★ 只读: 只查 aggregator.db，绝不写。

协议要点（MCP 2024-11-05）:
   · 传输: stdio · 每行一个 JSON-RPC 2.0 消息（LSP 风格的 Content-Length 不是 MCP 的规定，
     MCP 的 stdio 传输用【行分隔 JSON】）
   · 握手: initialize → （通知）notifications/initialized
   · 方法: tools/list · tools/call · ping
"""
import json
import os
import re
import sqlite3
import sys

DB = (os.environ.get('ANCLUM_DB')
      or os.environ.get('SKILLTIDE_DB')
      or '/opt/dsh-app/var/aggregator.db')
SERVER_NAME = 'anclum'
SERVER_VERSION = '0.2.0'
PROTOCOL = '2024-11-05'

TOOLS = [
    {
        'name': 'search_tools',
        'description': ('Search Anclum\'s catalogue of 8,250 MCP servers, agent skills and '
                        'open-source AI projects, plus 1,500 AI tools. Returns name, url, '
                        'one-line summary and tags. Read-only.'),
        'inputSchema': {
            'type': 'object',
            'properties': {
                'query': {'type': 'string',
                          'description': 'What you are looking for, e.g. "kubernetes", '
                                         '"video editing", "写小说"'},
                'category': {'type': 'string',
                             'description': 'Optional: limit to one AI-tool category slug '
                                            '(e.g. ai-writing) or a field tag (e.g. MCP 服务)'},
                'limit': {'type': 'integer', 'description': 'Max results (default 10, max 50)'},
            },
            'required': ['query'],
        },
    },
    {
        'name': 'get_tool',
        'description': ('Get one catalogue entry by its key (the slug used in its Anclum URL). '
                        'Returns the full record: name, url, description, tags, source, '
                        'first/last seen. Read-only.'),
        'inputSchema': {
            'type': 'object',
            'properties': {'key': {'type': 'string', 'description': 'The entry key/slug'}},
            'required': ['key'],
        },
    },
    {
        'name': 'list_categories',
        'description': ('List the catalogue\'s taxonomies: AI-tool categories (with counts) and '
                        'field tags (e.g. "MCP 服务", "Agent 技能"). Useful for then calling '
                        'search_tools with a category. Read-only.'),
        'inputSchema': {'type': 'object', 'properties': {}},
    },
]


class DbMissing(Exception):
    """★ task-206: 目录库不存在 —— 用一个明确的异常类型，让上层给【人话错误】。"""


def connect():
    # ★ task-206（Glama 门槛要求"能独立启动"）: 在没有目录库的环境里
    #   （Glama 沙箱 / 别人 git clone 后），原来会抛
    #   "OperationalError: unable to open database file" —— 那是栈内术语，
    #   使用者不知道该怎么办。⇒ 改成【明确的前置检查 + 人话错误】。
    #   ★ initialize / tools/list 【不碰库】，所以仍然正常（Glama 的 introspection 只要这个）。
    if not os.path.exists(DB):
        raise DbMissing(
            f'catalogue database not found at {DB}. '
            f'Set ANCLUM_DB to the path of your copy of the SQLite catalogue '
            f'(see README, section Configuration).')
    c = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    c.row_factory = sqlite3.Row
    return c


def _rows(sql, args=()):
    c = connect()
    try:
        return [dict(r) for r in c.execute(sql, args)]
    finally:
        c.close()


def _entry(r, kind):
    """统一成 MCP 客户端好读的形状。"""
    out = {
        'key': r.get('key'),
        'name': r.get('name'),
        'url': r.get('url'),
        # ★ 两个表的列名不同: items.one_line / ai_tools.one_liner
        'one_line': ((r.get('one_line') or r.get('one_liner') or '')).strip(),
        'kind': kind,
    }
    if kind == 'catalogue':
        try:
            out['fields'] = [f for f in json.loads(r.get('fields') or '[]') if f][:6]
        except Exception:
            out['fields'] = []
        out['first_seen'] = r.get('first_seen')
        out['last_seen'] = r.get('last_seen')
        out['anclum_url'] = f"https://anclum.com/en/s/{r.get('key')}/"
        out['skilltide_url'] = out['anclum_url']  # legacy name, kept so existing clients do not break
    else:
        out['category'] = r.get('category')
        out['cn_ui'] = ((r.get('cn_verdict') or '') == '中文界面')
        out['icp_filed'] = bool((r.get('icp') or '').strip())
        out['price'] = r.get('price_tier') or 'unknown'
        out['anclum_url'] = f"https://anclum.com/en/ai/{r.get('category')}/"
        out['skilltide_url'] = out['anclum_url']  # legacy name, kept so existing clients do not break
    return out


def tool_search(args):
    q = (args.get('query') or '').strip()
    if not q:
        return {'error': 'query is required'}
    lim = args.get('limit') or 10
    try:
        lim = max(1, min(50, int(lim)))
    except Exception:
        lim = 10
    cat = (args.get('category') or '').strip()
    # ★ 分词 OR 匹配（修我自己报的不足）:
    #   纯 LIKE 子串匹配对【带空格的自然语言】匹配率低 ——
    #   实测 '做 PPT' 只返回 1 条，而 'PPT' 返回 6 条。
    #   AI agent 用自然语言问是常态（"我要做 PPT"）⇒ 按空格/CJK 标点切词，
    #   【所有词都要出现】（AND of tokens）比"整串子串"宽容，比"任一 token"精确。
    toks = [t for t in re.split(r'[\s,，。、/|]+', q) if t]
    if not toks:
        toks = [q]
    like = f'%{q}%'          # 整串（用于排序：整串命中排前面）
    res = []
    # ① 目录条目（MCP/技能/开源）
    # ★ 注意两个表的列名不同: items.one_line / ai_tools.one_liner
    #   （我第一版混用 ⇒ "no such column: one_line" ⇒ search_tools 对目录条目全挂）
    where = ["COALESCE(hidden,0)=0"]
    a = []
    for t in toks:
        where.append("(name LIKE ? OR one_line LIKE ? OR fields LIKE ?)")
        a += [f'%{t}%'] * 3
    if cat:
        where.append("fields LIKE ?")
        a.append(f'%{cat}%')
    sql = ("SELECT key,name,url,one_line,fields,first_seen,last_seen FROM items WHERE "
           + " AND ".join(where)
           + " ORDER BY (CASE WHEN name LIKE ? THEN 0 ELSE 1 END), name LIMIT ?")
    a += [like, lim]
    for r in _rows(sql, tuple(a)):
        res.append(_entry(r, 'catalogue'))
    # ② AI 工具
    if len(res) < lim:
        # ★ 第二个 bug: ai_tools 的列叫 one_liner（不是 one_line），
        #   而且我第一版的 SELECT 里根本没选描述列 ⇒ _entry 拿不到 one_line。
        where2 = ["COALESCE(hidden,0)=0"]
        a2 = []
        for t in toks:
            where2.append("(name LIKE ? OR one_liner LIKE ?)")
            a2 += [f'%{t}%'] * 2
        if cat:
            where2.append("category = ?")
            a2.append(cat)
        sql2 = ("SELECT key,name,clean_url AS url,one_liner,category,cn_verdict,icp,price_tier "
                "FROM ai_tools WHERE " + " AND ".join(where2)
                + " ORDER BY (CASE WHEN name LIKE ? THEN 0 ELSE 1 END), name LIMIT ?")
        a2 += [like, lim - len(res)]
        for r in _rows(sql2, tuple(a2)):
            res.append(_entry(r, 'ai_tool'))
    # ★ 回退: AND（所有 token 都要命中）有时太严 ——
    #   实测 '我要做 PPT' 分词成 ['我要做','PPT']，'我要做' 匹配不到任何条目 ⇒ 0 条。
    #   ⇒ 若 AND 无结果、且 token 多于 1 个，则【退回 OR】（任一 token 命中）。
    #   ★ 这是"先精确后宽松"：精确有结果就不放宽（避免噪音），没结果才放宽。
    #   ★ 2026-10-28: 两处修正
    #     ① 返回体加 match='any'，让调用方知道结果来自放宽那一遍（此前是静默的）。
    #     ② 放宽后【按命中 token 数排序】，不再只按 name —— 否则一个废词加一个常用词
    #        会返回字母序最前的条目（实测 query='zzzq mcp' 全是 06ketan/* 这类）。
    relaxed = False
    if not res and len(toks) > 1:
        relaxed = True
        parts, score, pa = [], [], []
        for t in toks:
            parts.append("(name LIKE ? OR one_line LIKE ? OR fields LIKE ?)")
            score.append("(CASE WHEN (name LIKE ? OR one_line LIKE ? OR fields LIKE ?) THEN 1 ELSE 0 END)")
            pa += [f'%{t}%'] * 3
        sql = ("SELECT key,name,url,one_line,fields,first_seen,last_seen, ("
               + " + ".join(score) + ") AS hits FROM items "
               "WHERE COALESCE(hidden,0)=0 AND ("
               + " OR ".join(parts) + ") ORDER BY hits DESC, length(name) ASC, name LIMIT ?")
        a = pa + pa + [lim]
        for r in _rows(sql, tuple(a)):
            res.append(_entry(r, 'catalogue'))
        if len(res) < lim:
            parts2, score2, pa2 = [], [], []
            for t in toks:
                parts2.append("(name LIKE ? OR one_liner LIKE ?)")
                score2.append("(CASE WHEN (name LIKE ? OR one_liner LIKE ?) THEN 1 ELSE 0 END)")
                pa2 += [f'%{t}%'] * 2
            sql2 = ("SELECT key,name,clean_url AS url,one_liner,category,cn_verdict,icp,price_tier, ("
                    + " + ".join(score2) + ") AS hits FROM ai_tools "
                    "WHERE COALESCE(hidden,0)=0 AND ("
                    + " OR ".join(parts2) + ") ORDER BY hits DESC, length(name) ASC, name LIMIT ?")
            a2 = pa2 + pa2 + [lim - len(res)]
            for r in _rows(sql2, tuple(a2)):
                res.append(_entry(r, 'ai_tool'))
    return {'query': q, 'tokens': toks, 'category': cat or None,
            'match': 'any' if relaxed else 'all',
            'count': len(res), 'results': res}


def tool_get(args):
    key = (args.get('key') or '').strip()
    if not key:
        return {'error': 'key is required'}
    rs = _rows("SELECT * FROM items WHERE key=? AND COALESCE(hidden,0)=0", (key,))
    if rs:
        r = dict(rs[0])
        out = _entry(r, 'catalogue')
        out['description'] = (r.get('official_desc') or '').strip()[:1200]
        out['source'] = r.get('source')
        try:
            out['sources'] = json.loads(r.get('sources') or '[]')[:10]
        except Exception:
            out['sources'] = []
        out['install_cmd'] = (r.get('install_cmd') or '').strip() or None
        out['repo'] = (r.get('stars_own_repo') or '').strip() or None
        return out
    rs = _rows("SELECT * FROM ai_tools WHERE key=? AND COALESCE(hidden,0)=0", (key,))
    if rs:
        return _entry(dict(rs[0]), 'ai_tool')
    return {'error': f'not found: {key}'}


def tool_categories(_args):
    cats = _rows("SELECT category, COUNT(*) n FROM ai_tools WHERE COALESCE(hidden,0)=0 "
                 "GROUP BY category ORDER BY n DESC")
    # 领域标签（从 items.fields 聚合）
    from collections import Counter
    cnt = Counter()
    for r in _rows("SELECT fields FROM items WHERE COALESCE(hidden,0)=0"):
        try:
            for f in json.loads(r['fields'] or '[]'):
                if f:
                    cnt[f] += 1
        except Exception:
            pass
    return {
        'ai_tool_categories': [{'slug': c['category'], 'count': c['n']} for c in cats],
        'field_tags': [{'tag': k, 'count': v} for k, v in cnt.most_common(30)],
        'catalogue_total': len(_rows("SELECT 1 FROM items WHERE COALESCE(hidden,0)=0")),
        'ai_tool_total': sum(c['n'] for c in cats),
    }


HANDLERS = {'search_tools': tool_search, 'get_tool': tool_get, 'list_categories': tool_categories}


def send(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + '\n')
    sys.stdout.flush()


def reply(mid, result=None, error=None):
    m = {'jsonrpc': '2.0', 'id': mid}
    if error is not None:
        m['error'] = error
    else:
        m['result'] = result
    send(m)


def handle(msg):
    mid = msg.get('id')
    method = msg.get('method')
    params = msg.get('params') or {}
    if method == 'initialize':
        return reply(mid, {
            'protocolVersion': PROTOCOL,
            'capabilities': {'tools': {}},
            'serverInfo': {'name': SERVER_NAME, 'version': SERVER_VERSION},
        })
    if method in ('notifications/initialized', 'initialized'):
        return                      # 通知，无回复
    if method == 'ping':
        return reply(mid, {})
    if method == 'tools/list':
        return reply(mid, {'tools': TOOLS})
    if method == 'tools/call':
        name = params.get('name')
        args = params.get('arguments') or {}
        h = HANDLERS.get(name)
        if not h:
            return reply(mid, error={'code': -32602, 'message': f'unknown tool: {name}'})
        try:
            out = h(args)
        except DbMissing as e:
            # ★ 缺库不是"程序坏了"，是"还没配置" ⇒ 报清楚怎么配，而不是抛栈
            return reply(mid, {'content': [{'type': 'text', 'text': str(e)}],
                               'isError': True})
        except Exception as e:
            return reply(mid, {'content': [{'type': 'text',
                                            'text': f'error: {type(e).__name__}: {e}'}],
                               'isError': True})
        return reply(mid, {'content': [{'type': 'text',
                                        'text': json.dumps(out, ensure_ascii=False, indent=1)}],
                           'isError': False})
    if mid is not None:
        return reply(mid, error={'code': -32601, 'message': f'method not found: {method}'})


def main():
    # 逐行读 stdin（MCP stdio 传输 = 行分隔 JSON）
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            continue
        if isinstance(msg, list):        # 批量
            for m in msg:
                handle(m)
        else:
            handle(msg)
    return 0


if __name__ == '__main__':
    sys.exit(main())
