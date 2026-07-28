export type NodeType = "Person" | "Technology" | "Decision";

export interface MockCitation {
  id: string;
  marker: string;
  source_id: string;
  target_id: string;
}

export interface MockSource {
  source_id: string;
  raw_text: string;
  author: string;
  timestamp: string;
  source_type: "slack" | "git" | "jira";
}

export interface MockGraphNode {
  id: string;
  label: string;
  type: NodeType;
  timestamp: string;
  position?: { x: number; y: number };
}

export interface MockGraphEdge {
  id: string;
  source: string;
  target: string;
  relation: string;
  timestamp: string;
  source_ref: string;
}

export interface MockResponse {
  question: string;
  narrative: string;
  citations: MockCitation[];
  nodes: MockGraphNode[];
  edges: MockGraphEdge[];
  sources: MockSource[];
}

export const mockResponse: MockResponse = {
  question: "Why did we switch from AWS to GCP in 2023?",
  narrative:
    "The migration from AWS to GCP was driven by a convergence of cost pressure, platform reliability concerns, and a stronger engineering narrative around Kubernetes-native tooling. In early 2023, Sarah Chen began advocating for a change after repeated incidents in the AWS networking layer made multi-region failover feel brittle [1]. At the same time, the team saw that GCP’s managed services and regional resilience offered a more predictable operating model for the new analytics platform [2].\n\nBy Q2, the decision had become more concrete. The leadership team approved the migration after a series of architecture reviews, and the engineering organization aligned around a staged transition plan that emphasized minimizing risk without sacrificing delivery velocity [3]. The final push came when the platform team committed code to rehost the core services, replacing legacy AWS-only dependencies with GCP-backed infrastructure and observability tooling [4].",
  citations: [
    { id: "cit-1", marker: "[1]", source_id: "source-slack-1", target_id: "node-sarah" },
    { id: "cit-2", marker: "[2]", source_id: "source-jira-1", target_id: "edge-1" },
    { id: "cit-3", marker: "[3]", source_id: "source-slack-2", target_id: "edge-2" },
    { id: "cit-4", marker: "[4]", source_id: "source-git-1", target_id: "edge-3" },
  ],
  nodes: [
    { id: "node-sarah", label: "Sarah Chen", type: "Person", timestamp: "2023-01-12T09:00:00Z" },
    { id: "node-aws", label: "AWS", type: "Technology", timestamp: "2023-01-10T08:30:00Z" },
    { id: "node-gcp", label: "GCP", type: "Technology", timestamp: "2023-03-21T11:00:00Z" },
    { id: "node-k8s", label: "Kubernetes", type: "Technology", timestamp: "2023-04-17T15:00:00Z" },
    { id: "node-decision", label: "Move to GCP", type: "Decision", timestamp: "2023-06-01T16:45:00Z" },
  ],
  edges: [
    { id: "edge-1", source: "node-sarah", target: "node-gcp", relation: "ADVOCATED_FOR", timestamp: "2023-01-12T09:00:00Z", source_ref: "source-slack-1" },
    { id: "edge-2", source: "node-sarah", target: "node-decision", relation: "APPROVED", timestamp: "2023-06-01T16:45:00Z", source_ref: "source-slack-2" },
    { id: "edge-3", source: "node-gcp", target: "node-k8s", relation: "COMMITTED_CODE", timestamp: "2023-07-18T12:30:00Z", source_ref: "source-git-1" },
    { id: "edge-4", source: "node-aws", target: "node-gcp", relation: "REPLACED_BY", timestamp: "2023-08-01T09:00:00Z", source_ref: "source-jira-1" },
  ],
  sources: [
    {
      source_id: "source-slack-1",
      raw_text: "Sarah: The AWS networking layer is causing regional failover issues and I think the GCP managed networking story is more resilient.",
      author: "Sarah Chen",
      timestamp: "2023-01-12T09:00:00Z",
      source_type: "slack",
    },
    {
      source_id: "source-slack-2",
      raw_text: "Leadership review: Approved the staged migration to GCP after architecture review and risk mitigation planning.",
      author: "Mina Patel",
      timestamp: "2023-06-01T16:45:00Z",
      source_type: "slack",
    },
    {
      source_id: "source-jira-1",
      raw_text: "JIRA-884: Standardize the platform on GCP and retire the AWS-only deployment path by Q4.",
      author: "DevOps Team",
      timestamp: "2023-03-21T11:00:00Z",
      source_type: "jira",
    },
    {
      source_id: "source-git-1",
      raw_text: "commit 8f3b9ce: Rehost analytics services to GCP, add regional observability and Kubernetes-ready deployment manifests.",
      author: "Omar Ruiz",
      timestamp: "2023-07-18T12:30:00Z",
      source_type: "git",
    },
  ],
};
