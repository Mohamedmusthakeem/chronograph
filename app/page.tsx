"use client";

import { useEffect, useMemo, useState } from "react";
import ReactFlow, { Background, Controls, MarkerType, Position, type Edge, type Node } from "reactflow";
import "reactflow/dist/style.css";
import { mockResponse, type MockCitation, type MockGraphEdge, type MockGraphNode, type MockSource } from "@/lib/mockResponses";

type Message = {
  id: number;
  role: "user" | "assistant";
  content: string;
};

type BackendResponse = {
  question: string;
  narrative: string;
  citations: MockCitation[];
  nodes: MockGraphNode[];
  edges: MockGraphEdge[];
  sources: MockSource[];
};

const nodeColors: Record<string, string> = {
  Person: "#7c3aed",
  Technology: "#2563eb",
  Decision: "#059669",
};

const examplePrompts = [
  "What did Sarah say about the migration?",
  "What concerns were raised about IAM?",
  "How did the decision to move to GCP unfold?",
];

const apiBaseCandidates = ["http://localhost:8000", "http://localhost:8001", "http://localhost:8002"];

const sampleApiCalls = [
  { label: "Health check", endpoint: "/health" },
  { label: "Smoke test", endpoint: "/smoke" },
];

function NarrativeContent({
  narrative,
  citations,
  onCitationClick,
}: {
  narrative: string;
  citations: Array<{ marker: string; source_id: string }>;
  onCitationClick: (sourceId: string) => void;
}) {
  const parts = narrative.split(/(\[[0-9]+\])/g);

  return (
    <>
      {parts.map((part, index) => {
        const citation = citations.find((item) => item.marker === part);
        if (!citation) {
          return <span key={`${part}-${index}`}>{part}</span>;
        }

        return (
          <button
            key={`${citation.source_id}-${index}`}
            type="button"
            className="ml-1 align-super text-xs font-semibold text-indigo-600 underline decoration-indigo-400 underline-offset-2"
            onClick={() => onCitationClick(citation.source_id)}
          >
            {part}
          </button>
        );
      })}
    </>
  );
}

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([
    { id: 1, role: "assistant", content: mockResponse.narrative },
  ]);
  const [draft, setDraft] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [activeCitationId, setActiveCitationId] = useState<string | null>(null);
  const [backendResponse, setBackendResponse] = useState<BackendResponse | null>(null);
  const [backendError, setBackendError] = useState<string | null>(null);
  const [backendStatus, setBackendStatus] = useState<"checking" | "online" | "offline">("checking");
  const [assistantCitations, setAssistantCitations] = useState<MockCitation[]>(mockResponse.citations);
  const [apiPreview, setApiPreview] = useState<string>("Run a sample request to view the API response preview here.");

  const runSampleRequest = async (endpoint: string) => {
    try {
      const payload = await fetchBackendJson(endpoint);
      setApiPreview(JSON.stringify(payload, null, 2));
    } catch {
      setApiPreview("The backend is not reachable from the browser yet. Start the FastAPI service and try again.");
    }
  };

  const fetchBackendJson = async (path: string) => {
    let lastError: unknown;

    for (const baseUrl of apiBaseCandidates) {
      try {
        const response = await fetch(`${baseUrl}${path}`);
        if (!response.ok) {
          throw new Error("Backend request failed");
        }
        return await response.json();
      } catch (error) {
        lastError = error;
      }
    }

    throw lastError ?? new Error("Backend unavailable");
  };

  const resetConversation = () => {
    setMessages([{ id: 1, role: "assistant", content: mockResponse.narrative }]);
    setDraft("");
    setActiveCitationId(null);
    setBackendResponse(null);
    setBackendError(null);
    setAssistantCitations(mockResponse.citations);
  };

  useEffect(() => {
    const loadHealth = async () => {
      try {
        await fetchBackendJson("/health");
        setBackendStatus("online");
      } catch {
        setBackendStatus("offline");
        setBackendError("The local API is not reachable yet. Showing the mock experience while the backend boots up.");
      }
    };

    loadHealth();
  }, []);

  const activeSource = useMemo(() => {
    const sourceList = backendResponse?.sources ?? mockResponse.sources;
    return sourceList.find((source: MockSource) => source.source_id === activeCitationId) ?? null;
  }, [activeCitationId, backendResponse]);

  const timelineEntries = useMemo(() => {
    const sourceList = (backendResponse?.sources ?? mockResponse.sources).slice().sort((left, right) => new Date(left.timestamp).getTime() - new Date(right.timestamp).getTime());

    return sourceList.map((source: MockSource) => ({
      ...source,
      isActive: source.source_id === activeCitationId,
    }));
  }, [activeCitationId, backendResponse]);

  const graphNodes = useMemo<Node[]>(() => {
    const nodes = backendResponse?.nodes ?? mockResponse.nodes;
    return nodes.map((node: MockGraphNode, index: number) => ({
      id: node.id,
      position: node.position ?? { x: index * 220, y: index % 2 === 0 ? 80 : 240 },
      data: { label: node.label, type: node.type, timestamp: node.timestamp },
      style: {
        background: nodeColors[node.type] ?? "#111827",
        color: "#f9fafb",
        border: "1px solid rgba(255,255,255,0.2)",
        borderRadius: 999,
        padding: "12px 16px",
        minWidth: 140,
      },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
    }));
  }, [backendResponse]);

  const graphEdges = useMemo<Edge[]>(() => {
    const edges = backendResponse?.edges ?? mockResponse.edges;
    return edges.map((edge: MockGraphEdge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      label: `${edge.relation} · ${new Date(edge.timestamp).toLocaleDateString("en", { month: "short", day: "numeric", year: "numeric" })}`,
      animated: edge.source_ref === activeCitationId,
      data: { sourceRef: edge.source_ref, relation: edge.relation },
      markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18 },
      style: {
        stroke: edge.source_ref === activeCitationId ? "#7c3aed" : "#94a3b8",
        strokeWidth: edge.source_ref === activeCitationId ? 3 : 1.5,
      },
    }));
  }, [activeCitationId, backendResponse]);

  const nodeTypes = useMemo(() => ({}), []);
  const edgeTypes = useMemo(() => ({}), []);

  const handleSend = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!draft.trim()) return;

    const userMessage: Message = { id: Date.now(), role: "user", content: draft.trim() };
    setMessages((prev) => [...prev, userMessage]);
    setDraft("");
    setIsLoading(true);
    setBackendError(null);

    try {
      let lastError: unknown;
      let data: BackendResponse | null = null;

      for (const baseUrl of apiBaseCandidates) {
        try {
          const response = await fetch(`${baseUrl}/query`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              question: draft.trim(),
              history: messages.map((message) => ({ role: message.role, content: message.content })),
            }),
          });

          if (!response.ok) {
            throw new Error("Backend request failed");
          }

          data = await response.json();
          break;
        } catch (error) {
          lastError = error;
        }
      }

      if (!data) {
        throw lastError ?? new Error("Backend request failed");
      }
      setBackendStatus("online");
      setBackendResponse(data);
      setAssistantCitations(data.citations);
      setMessages((prev) => [...prev, { id: Date.now() + 1, role: "assistant", content: data.narrative }]);
    } catch {
      setBackendStatus("offline");
      setBackendResponse(null);
      setAssistantCitations(mockResponse.citations);
      setMessages((prev) => [...prev, { id: Date.now() + 1, role: "assistant", content: mockResponse.narrative }]);
      setBackendError("The backend is not answering yet, so the mock narrative is being shown for now.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top_left,_rgba(99,102,241,0.14),_transparent_28%),linear-gradient(135deg,_#f8fafc_0%,_#eef2ff_100%)] p-4 text-slate-800 sm:p-6 lg:p-8">
      <div className="mx-auto flex max-w-7xl flex-col gap-6">
        <header className="rounded-3xl border border-slate-200/70 bg-white/80 px-6 py-5 shadow-sm backdrop-blur">
          <div className="flex flex-col gap-2 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <p className="text-sm font-medium uppercase tracking-[0.25em] text-indigo-600">ChronoGraph</p>
              <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Temporal graph forensics for engineering decisions</h1>
            </div>
            <div className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-sm font-medium text-emerald-700">
              Mock Phase 1 • Interactive UI
            </div>
          </div>
        </header>

        <section className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
          <div className="flex min-h-[700px] flex-col rounded-3xl border border-slate-200/70 bg-white/90 shadow-sm">
            <div className="border-b border-slate-200/80 p-4 sm:p-5">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-semibold text-slate-900">Investigation workspace</h2>
                  <p className="text-sm text-slate-500">Ask a question and inspect the supporting evidence in context.</p>
                </div>
                <div className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium uppercase tracking-[0.2em] text-slate-600">
                  Phase 1
                </div>
              </div>
            </div>

            <div className="flex-1 space-y-4 overflow-y-auto p-4 sm:p-5">
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-3">
                <div className="mb-2 flex items-center justify-between">
                  <p className="text-sm font-semibold text-slate-900">Live API samples</p>
                  <span className="text-xs font-medium uppercase tracking-[0.2em] text-slate-500">Quick checks</span>
                </div>
                <div className="flex flex-wrap gap-2">
                  {sampleApiCalls.map((sample) => (
                    <button
                      key={sample.label}
                      type="button"
                      onClick={() => runSampleRequest(sample.endpoint)}
                      className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:border-indigo-300 hover:text-indigo-700"
                    >
                      {sample.label}
                    </button>
                  ))}
                </div>
                <pre className="mt-3 overflow-x-auto rounded-xl bg-slate-900 p-3 text-xs text-slate-100">{apiPreview}</pre>
              </div>
              <div className={`rounded-2xl border px-3 py-2 text-sm ${backendStatus === "online" ? "border-emerald-200 bg-emerald-50 text-emerald-700" : backendStatus === "offline" ? "border-amber-200 bg-amber-50 text-amber-700" : "border-slate-200 bg-slate-50 text-slate-600"}`}>
                {backendStatus === "checking" ? "Checking backend connectivity…" : backendStatus === "online" ? "Backend connected. Responses are coming from the local API." : "Backend offline. The mock experience is currently active."}
              </div>
              {backendError ? (
                <div className="rounded-2xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-700">
                  {backendError}
                </div>
              ) : null}
              {messages.map((message) => (
                <div key={message.id} className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}>
                  <div className={`max-w-[90%] rounded-2xl px-4 py-3 text-sm leading-7 shadow-sm ${message.role === "user" ? "bg-slate-900 text-white" : "bg-slate-50 text-slate-700"}`}>
                    {message.role === "assistant" ? (
                      <div className="space-y-3">
                        <div className="text-[15px] leading-8 text-slate-700">
                          <NarrativeContent
                            narrative={message.content}
                            citations={assistantCitations}
                            onCitationClick={(sourceId) => setActiveCitationId(sourceId)}
                          />
                        </div>
                      </div>
                    ) : (
                      <p>{message.content}</p>
                    )}
                  </div>
                </div>
              ))}

              {isLoading ? (
                <div className="flex justify-start">
                  <div className="rounded-2xl bg-slate-50 px-4 py-3 text-sm text-slate-600 shadow-sm">
                    Thinking through the evidence and preparing the timeline…
                  </div>
                </div>
              ) : null}
            </div>

            <form onSubmit={handleSend} className="border-t border-slate-200/80 bg-slate-50/80 p-4 sm:p-5">
              <div className="flex flex-col gap-3 sm:flex-row">
                <input
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  placeholder="Ask about the AWS to GCP transition..."
                  className="flex-1 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none ring-0 transition focus:border-indigo-400"
                />
                <button type="submit" className="rounded-2xl bg-indigo-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-indigo-500">
                  Send
                </button>
              </div>

              <div className="mt-3 flex flex-wrap gap-2">
                {examplePrompts.map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    onClick={() => setDraft(prompt)}
                    className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:border-indigo-300 hover:text-indigo-700"
                  >
                    {prompt}
                  </button>
                ))}
                <button
                  type="button"
                  onClick={resetConversation}
                  className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:border-rose-300 hover:text-rose-700"
                >
                  Reset
                </button>
              </div>
            </form>
          </div>

          <div className="flex min-h-[700px] flex-col rounded-3xl border border-slate-200/70 bg-white/90 shadow-sm">
            <div className="border-b border-slate-200/80 p-4 sm:p-5">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-semibold text-slate-900">Temporal graph</h2>
                  <p className="text-sm text-slate-500">Nodes and edges surface the chain of evidence across time.</p>
                </div>
              </div>
            </div>

            <div className="flex-1 p-3">
              <div className="h-[420px] rounded-2xl border border-slate-200 bg-slate-50/80 p-2">
                <ReactFlow
                  nodes={graphNodes}
                  edges={graphEdges}
                  nodeTypes={nodeTypes}
                  edgeTypes={edgeTypes}
                  fitView
                  nodesDraggable
                  edgesFocusable
                  onEdgeClick={(_, edge) => setActiveCitationId(edge.data?.sourceRef ?? null)}
                  proOptions={{ hideAttribution: true }}
                >
                  <Background gap={16} size={1} />
                  <Controls />
                </ReactFlow>
              </div>
            </div>

            <div className="border-t border-slate-200/80 p-4 sm:p-5">
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                {activeSource ? (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <p className="text-sm font-semibold text-slate-900">Selected evidence</p>
                      <span className="rounded-full bg-indigo-100 px-2.5 py-1 text-xs font-medium uppercase tracking-[0.2em] text-indigo-700">
                        {activeSource.source_type}
                      </span>
                    </div>
                    <p className="text-sm leading-7 text-slate-700">{activeSource.raw_text}</p>
                    <div className="flex flex-wrap gap-3 text-xs text-slate-500">
                      <span>Author: {activeSource.author}</span>
                      <span>{new Date(activeSource.timestamp).toLocaleString()}</span>
                    </div>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <p className="text-sm font-semibold text-slate-900">Click a citation or graph edge to inspect the source snippet.</p>
                    <p className="text-sm leading-7 text-slate-600">The selected edge will highlight in the graph when evidence is opened, and the backend status above shows whether live responses are available.</p>
                  </div>
                )}
              </div>

              <div className="mt-4 rounded-2xl border border-slate-200 bg-white/80 p-3">
                <div className="mb-2 flex items-center justify-between">
                  <p className="text-sm font-semibold text-slate-900">Evidence timeline</p>
                  <span className="text-xs font-medium uppercase tracking-[0.2em] text-slate-500">Chronological</span>
                </div>
                <div className="space-y-2">
                  {timelineEntries.map((entry) => (
                    <button
                      key={entry.source_id}
                      type="button"
                      onClick={() => setActiveCitationId(entry.source_id)}
                      className={`flex w-full items-start justify-between rounded-xl border px-3 py-2 text-left text-sm transition ${entry.isActive ? "border-indigo-300 bg-indigo-50 text-indigo-700" : "border-transparent bg-slate-50 text-slate-600 hover:border-slate-200 hover:bg-slate-100"}`}
                    >
                      <span className="pr-3">
                        <span className="block font-medium">{entry.author}</span>
                        <span className="mt-0.5 block text-xs opacity-80">{entry.raw_text}</span>
                      </span>
                      <span className="shrink-0 text-xs uppercase tracking-[0.2em] opacity-70">{entry.source_type}</span>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
