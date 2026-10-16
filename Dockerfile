# skilltide-mcp — minimal stdio MCP server image
#
# ★ Why this image is tiny: the server has ZERO dependencies (Python standard library
#   only — json / os / re / sqlite3 / sys). There is no pip install step, no requirements.txt.
#
# ★ Transport is stdio, not HTTP — so there is deliberately no EXPOSE and no port.
#   The client (Claude Desktop, Cursor, …) launches this container and speaks
#   newline-delimited JSON-RPC over stdin/stdout.
#
# ★ Introspection works with no data: `initialize` and `tools/list` never touch the
#   catalogue, so the server starts and answers introspection in a sandbox that has no
#   database at all. Only the data-returning tools need SKILLTIDE_DB (see below).

FROM python:3.12-slim

WORKDIR /app

# The whole server is one file. Copy it first so a source change only rebuilds one layer.
COPY skilltide_mcp.py /app/skilltide_mcp.py

# Unbuffered stdout matters for stdio transport: without -u, Python buffers and the
# client can wait for a reply that is still sitting in the buffer.
ENV PYTHONUNBUFFERED=1

# The catalogue is NOT baked into the image. This image is generic; point it at your own
# copy of the SQLite catalogue (schema: `items` and `ai_tools`). Mount it read-only:
#
#   docker run -i --rm \
#     -v /path/to/aggregator.db:/data/aggregator.db:ro \
#     -e SKILLTIDE_DB=/data/aggregator.db \
#     skilltide-mcp
#
# With no SKILLTIDE_DB the server still starts and answers initialize / tools/list;
# the data tools return a clear "catalogue database not found … set SKILLTIDE_DB" message.
ENV SKILLTIDE_DB=/data/aggregator.db

ENTRYPOINT ["python3", "-u", "/app/skilltide_mcp.py"]
