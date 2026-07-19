"""Contract checks for the self-contained FlowProof portfolio demo."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "docs" / "index.html"


class StaticDemoContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = DEMO.read_text(encoding="utf-8")

    def test_demo_is_honest_and_self_contained(self) -> None:
        self.assertIn("not a live product", self.html)
        self.assertRegex(self.html, r"No backend\s+(?:is running|runs)")
        self.assertNotRegex(self.html, r"<(?:script|img)[^>]+\bsrc\s*=")
        self.assertNotRegex(self.html, r"<link[^>]+\bhref\s*=")
        self.assertNotRegex(
            self.html, r"\b(?:fetch|XMLHttpRequest|WebSocket)\s*\("
        )

    def test_four_scenarios_are_exposed_as_one_named_radio_group(self) -> None:
        values = re.findall(
            r'<input type="radio" name="scenario" value="([A-D])"', self.html
        )
        self.assertEqual(values, ["B", "A", "C", "D"])
        self.assertIn("<fieldset>", self.html)
        self.assertIn("<legend>Scenario (inbound webhook)</legend>", self.html)

    def test_grid_cards_can_shrink_at_mobile_widths(self) -> None:
        card_rule = re.search(r"\.card\s*\{(.*?)\}", self.html, re.S)
        self.assertIsNotNone(card_rule)
        self.assertIn("min-width: 0", card_rule.group(1))

    def test_idempotency_walkthrough_pins_the_http_contract(self) -> None:
        for claim in (
            "201 Created",
            "200 OK",
            '"duplicate": <span class="dup-false">false</span>',
            '"duplicate": <span class="dup-true">true</span>',
            "the same workflow, nothing new created",
        ):
            self.assertIn(claim, self.html)

    def test_third_failure_is_dead_letter_in_every_visible_field(self) -> None:
        third_attempt = re.search(
            r'\{ node: "retry", attempt: 3, ledger: \{([^\n]+)\} \}', self.html
        )
        self.assertIsNotNone(third_attempt)
        self.assertIn('state: "dead_letter"', third_attempt.group(1))
        self.assertIn('cls: "s-bad"', third_attempt.group(1))
        self.assertIn('event: "workflow_dead_lettered"', self.html)

    def test_ai_assist_stops_for_human_review_instead_of_auto_approving(self) -> None:
        scenario = re.search(r"\n    D: \{(.*?)\n    \}\n  \};", self.html, re.S)
        self.assertIsNotNone(scenario)
        self.assertIn('state: "pending_approval"', scenario.group(1))
        self.assertNotIn("workflow_approved", scenario.group(1))

    def test_live_region_announces_domain_states_not_diagram_ids(self) -> None:
        self.assertIn('role="status" aria-live="polite"', self.html)
        self.assertIn(
            "finalState = step.ledger ? step.ledger.state : step.node;", self.html
        )
        self.assertIn(
            '"Scenario complete. Final state: " + finalState + "."', self.html
        )


if __name__ == "__main__":
    unittest.main()
