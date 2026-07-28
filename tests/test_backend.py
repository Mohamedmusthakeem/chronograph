import unittest

from backend.main import build_graph_response, load_triples


class BackendGraphResponseTests(unittest.TestCase):
    def test_follow_up_question_returns_evidence_based_response(self) -> None:
        response = build_graph_response("What did Sarah say about it?", [])
        self.assertIn("Sarah", response["narrative"])
        self.assertGreaterEqual(len(response["citations"]), 1)
        self.assertGreaterEqual(len(response["nodes"]), 1)
        self.assertGreaterEqual(len(response["edges"]), 1)

    def test_load_triples_reads_processed_evidence_graph(self) -> None:
        payload = load_triples()
        self.assertIn("entities", payload)
        self.assertIn("relations", payload)
        self.assertGreaterEqual(len(payload["relations"]), 1)

    def test_graph_response_includes_layout_positions(self) -> None:
        response = build_graph_response("What did Sarah say about it?", [])
        self.assertTrue(response["nodes"])
        self.assertIn("position", response["nodes"][0])


if __name__ == "__main__":
    unittest.main()
