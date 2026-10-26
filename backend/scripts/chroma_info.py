"""List the ChromaDB collections with chunk counts per source, and print a few sample chunks.

  .venv/bin/python scripts/chroma_info.py                 # all collections
  .venv/bin/python scripts/chroma_info.py "Module 6"      # also show 3 chunks of sources containing that text

Reads Chroma at localhost:8001 (the port docker compose publishes); override with CHROMA_URL=host:port.
"""

import collections
import os
import sys

import chromadb

host, _, port = os.environ.get("CHROMA_URL", "localhost:8001").partition(":")
client = chromadb.HttpClient(host=host, port=int(port or 8001))
needle = sys.argv[1].lower() if len(sys.argv) > 1 else None

for c in client.list_collections():
    col = client.get_collection(c.name)
    got = col.get(include=["metadatas"])
    per_source = collections.Counter(m["source"] for m in got["metadatas"])
    print(f"\n{col.name}: {col.count()} chunks, {len(per_source)} sources")
    for source, n in sorted(per_source.items()):
        print(f"  {n:5d}  {source}")
        if needle and needle in source.lower():
            s = col.get(where={"source": source}, limit=3, include=["documents", "metadatas"])
            for doc, meta in zip(s["documents"], s["metadatas"], strict=True):
                print(f"         [{meta['heading']}] {doc[:160].strip()!r}")
