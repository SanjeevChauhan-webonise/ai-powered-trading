"use client";

import { LoaderCircle } from "lucide-react";
import { useRef, useState } from "react";

import { ErrorNote, PageHeader } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  api,
  type ChunkPage,
  type KnowledgeChunk,
  type KnowledgeDoc,
} from "@/lib/api";
import { useLoad } from "@/lib/use-load";

export default function KnowledgePage() {
  const { data: docs, error: loadError, setData } = useLoad(api.knowledgeDocs);
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<KnowledgeChunk[] | null>(null);
  const [busy, setBusy] = useState<"search" | "upload" | "ingest" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const file = useRef<HTMLInputElement>(null);
  const [openDoc, setOpenDoc] = useState<string | null>(null);
  const [pages, setPages] = useState<Record<string, ChunkPage>>({});

  // Browse the stored chunks of one document, 20 at a time
  async function browse(source: string, more = false) {
    if (!more && openDoc === source) {
      setOpenDoc(null);
      return;
    }
    setOpenDoc(source);
    const have = more ? pages[source] : undefined;
    if (!more && pages[source]) return;
    setError(null);
    try {
      const next = await api.knowledgeChunks(
        source,
        have ? have.chunks.length : 0,
        20,
      );
      setPages((p) => ({
        ...p,
        [source]: have
          ? { ...next, offset: 0, chunks: [...have.chunks, ...next.chunks] }
          : next,
      }));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function guard(
    kind: "search" | "upload" | "ingest",
    fn: () => Promise<void>,
  ) {
    setBusy(kind);
    setError(null);
    setInfo(null);
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }
  const refresh = async () =>
    setData((await api.knowledgeDocs()) as KnowledgeDoc[]);

  return (
    <main className="mx-auto max-w-5xl space-y-5 p-6">
      <PageHeader
        title="Knowledge Base"
        description="The notes the research agent reads (RAG): options basics, indicators, risk, price action. Add your own .md or .pdf."
        action={
          <div className="flex gap-2">
            <input
              ref={file}
              type="file"
              accept=".md,.pdf"
              hidden
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f)
                  void guard("upload", async () => {
                    const r = await api.knowledgeUpload(f);
                    setInfo(`Added ${r.source} (${r.chunks} chunks)`);
                    await refresh();
                  });
                e.target.value = "";
              }}
            />
            <Button
              variant="outline"
              size="lg"
              disabled={busy !== null}
              onClick={() => file.current?.click()}
            >
              {busy === "upload" && <LoaderCircle className="animate-spin" />}{" "}
              Upload .md / .pdf
            </Button>
            <Button
              variant="outline"
              size="lg"
              disabled={busy !== null}
              onClick={() =>
                void guard("ingest", async () => {
                  await api.knowledgeIngest();
                  setInfo("Re-synced.");
                  await refresh();
                })
              }
            >
              {busy === "ingest" && <LoaderCircle className="animate-spin" />}{" "}
              Re-ingest
            </Button>
          </div>
        }
      />
      {(error || loadError) && <ErrorNote message={(error ?? loadError)!} />}
      {info && (
        <p className="rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
          {info}
        </p>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Search the knowledge base</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (q.trim())
                void guard("search", async () =>
                  setHits(await api.knowledgeSearch(q, 5)),
                );
            }}
          >
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="e.g. trailing stop, support and resistance, theta decay"
              className="h-10 bg-background"
            />
            <Button
              type="submit"
              size="lg"
              className="h-10"
              disabled={busy !== null}
            >
              {busy === "search" && <LoaderCircle className="animate-spin" />}{" "}
              Search
            </Button>
          </form>
          {hits && hits.length === 0 && (
            <p className="text-sm text-muted-foreground">
              Nothing relevant found.
            </p>
          )}
          {hits?.map((h, i) => (
            <div key={i} className="rounded-lg border p-3 text-sm">
              <div className="mb-1 flex items-center justify-between gap-2 text-xs text-muted-foreground">
                <span>
                  <span className="font-mono">{h.source}</span> · {h.heading}
                </span>
                <span className="font-mono">score {h.score.toFixed(2)}</span>
              </div>
              <p className="whitespace-pre-wrap">{h.text}</p>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Documents {docs ? `(${docs.length})` : ""}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {docs && docs.length === 0 && (
            <p className="text-sm text-muted-foreground">
              Empty. Upload your .md or .pdf files above to build the knowledge
              base.
            </p>
          )}
          <ul className="divide-y text-sm">
            {docs?.map((d) => (
              <li key={d.source} className="py-2">
                <div className="flex items-center justify-between">
                  <button
                    type="button"
                    onClick={() => void browse(d.source)}
                    className="text-left font-mono hover:underline"
                  >
                    {openDoc === d.source ? "▾" : "▸"} {d.source}
                  </button>
                  <span className="flex items-center gap-3">
                    <span className="text-xs text-muted-foreground">
                      {d.chunks} chunks
                    </span>
                    <Badge
                      variant={
                        d.doc_type === "uploaded" ? "default" : "secondary"
                      }
                    >
                      {d.doc_type}
                    </Badge>
                  </span>
                </div>
                {openDoc === d.source && (
                  <div className="mt-2 space-y-2">
                    {!pages[d.source] && (
                      <p className="text-xs text-muted-foreground">Loading…</p>
                    )}
                    {pages[d.source]?.chunks.map((c) => (
                      <div
                        key={c.id}
                        className="rounded-lg bg-muted/50 p-3 text-xs"
                      >
                        <div className="mb-1 flex justify-between text-muted-foreground">
                          <span>
                            #{c.chunk_index} · {c.heading || "no heading"}
                          </span>
                          <span className="font-mono">{c.id}</span>
                        </div>
                        <p className="whitespace-pre-wrap">{c.text}</p>
                      </div>
                    ))}
                    {pages[d.source] &&
                      pages[d.source].chunks.length < pages[d.source].total && (
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => void browse(d.source, true)}
                        >
                          Show more ({pages[d.source].chunks.length} of{" "}
                          {pages[d.source].total})
                        </Button>
                      )}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </main>
  );
}
