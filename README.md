# Anclum

An MCP server that lets an AI agent search **Anclum** — a catalogue of 8,250 MCP servers,
agent skills and open-source AI projects, plus 1,500 AI tools for people who are not
developers.

Read-only. Zero dependencies. One file.

> The GitHub repository keeps its original name `skilltide-mcp` because the official MCP
> Registry entry, Glama listing and existing client configs reference it. The product is
> **Anclum** (site: <https://anclum.com>).

## Why this one is different

Most directories give you a name and a link. These are the things we actually verified
before putting an entry in — each of them is checkable from the server's own output:

- **Official links only.** Every AI-tool link points at the tool's own site. We measured
  1,501 links: **0 redirect/link-wrapper pages, 0 tracking parameters**. Many directories
  in this space pass through the affiliate or redirect URL they were given.
- **Provenance is visible.** `get_tool` returns how many sources listed an entry, when we
  first and last saw it, and the raw source field — so an agent (or a person) can judge
  freshness instead of trusting a rank.
- **Chinese-usability labels.** Each AI tool carries whether we verified a Chinese UI
  (`cn_ui`) and whether the site holds a Chinese MIIT filing (`icp_filed`) — the two
  things a Chinese-speaking user actually needs to know before clicking.
- **Thin pages are marked, not padded.** Entries without substantive content are
  `noindex` on the site and we do not claim otherwise here.

We do **not** claim this is the best or most complete directory — only that the above are
true and verifiable.

## Remote endpoint (no install needed)

Anclum is available as a hosted **Streamable HTTP** MCP server — nothing to install:

```json
{"mcpServers": {"anclum": {"url": "https://anclum.com/mcp"}}}
```

Listed in the **official MCP Registry** as `io.github.wdfdaivd/anclum`:

```bash
curl -s "https://registry.modelcontextprotocol.io/v0/servers?search=anclum"
```

Read-only, rate limited (10 req/min per IP, burst 20), and it answers in tens of
milliseconds:

| Tool | What it does |
|---|---|
| `search_tools` | Free-text search across 8,250 MCP servers, agent skills and open-source AI projects, plus 1,500 AI tools |
| `get_tool` | Fetch one catalogue entry by its key |
| `list_categories` | List the taxonomies with live counts |

Every result links to a **verified official URL** (no redirect pages, no tracking
parameters) and carries provenance: source count, first/last seen.

## Install & run

No dependencies — Python 3.10+ standard library only. Clone and run:

```bash
git clone https://github.com/wdfdaivd/skilltide-mcp.git
cd skilltide-mcp
python3 skilltide_mcp.py
```

It speaks MCP over **stdio** (newline-delimited JSON-RPC 2.0), protocol version
`2024-11-05`.

### Claude Desktop / Cursor

```json
{
  "mcpServers": {
    "anclum": {
      "command": "python3",
      "args": ["/absolute/path/to/skilltide_mcp.py"]
    }
  }
}
```

### Configuration

| Env var | Default | Meaning |
|---|---|---|
| `ANCLUM_DB` (legacy: `SKILLTIDE_DB`) | `/opt/dsh-app/var/aggregator.db` | Path to the SQLite catalogue (opened **read-only**) |

> The default path is our server's. For a local checkout, point `ANCLUM_DB` at your own
> copy of the SQLite file (schema: `items` and `ai_tools` tables).

## Tools

### `search_tools(query, category?, limit?)`

Search both catalogues. Splits the query into tokens and requires every token to match
(name, one-line summary or tags); if that returns nothing it retries with any token.
Chinese queries work.

```json
{
  "query": "kubectl",
  "count": 2,
  "results": [
    {"key": "rohitg00-kubectl-mcp-server", "name": "rohitg00/kubectl-mcp-server",
     "url": "https://github.com/rohitg00/kubectl-mcp-server", "kind": "catalogue",
     "fields": ["MCP 服务"], "anclum_url": "https://anclum.com/en/s/rohitg00-kubectl-mcp-server/"}
  ]
}
```

### `get_tool(key)`

Full record for one entry: description, tags, sources, first/last seen, install command
when the repository itself provided one (`install_cmd`, else `null` — we do not invent
commands), and the upstream repo.

### `list_categories()`

The two taxonomies, with counts: 15 AI-tool categories and 21 field tags
(e.g. `MCP 服务` 5,585 · `Agent 技能` 133). Use a value as `category` in `search_tools`.

## Data

| Source | Rows | What it is |
|---|---|---|
| `items` | 8,250 | MCP servers, agent skills, open-source AI projects |
| `ai_tools` | 1,500 | AI tools for end users — writing, image, video, office… |

The site is <https://anclum.com>. This server only reads; it writes nothing.

## Testing

```bash
python3 selftest.py
```

Starts the server as a real subprocess, speaks the stdio protocol, and asserts on the
actual results (not just "did not error") — 8 checks including a Chinese query, an
unknown-tool error, and `ping`.

## License

MIT