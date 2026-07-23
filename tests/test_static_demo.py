"""Contract checks for the self-contained FlowProof portfolio demo."""

from pathlib import Path
import re
import struct
import unittest


ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "docs" / "index.html"
CARD = ROOT / "docs" / "flowproof-social-card.png"
README = ROOT / "README.md"
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
RUNNER = ROOT / "run_tests.py"
DEV_REQUIREMENTS = ROOT / "requirements-dev.txt"

CARD_URL = "https://lancimoun.github.io/flowproof/flowproof-social-card.png"
CARD_ALT = (
    "Static FlowProof illustration: duplicate webhooks converge into one workflow, "
    "a deterministic switch sends risk to a human approval gate, three bounded "
    "failure markers end at dead letter, and each transition appends a tile to "
    "the audit track."
)


class StaticDemoContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = DEMO.read_text(encoding="utf-8")

    def test_demo_is_honest_and_self_contained(self) -> None:
        self.assertIn("not a live product", self.html)
        self.assertRegex(self.html, r"No backend\s+(?:is running|runs)")
        self.assertNotRegex(self.html, r"<(?:script|img)[^>]+\bsrc\s*=")
        self.assertNotRegex(
            self.html,
            r'<link[^>]+\brel="(?:stylesheet|preload|modulepreload)"',
        )
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

    def test_social_card_is_real_sized_and_propagated_to_every_surface(self) -> None:
        data = CARD.read_bytes()
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(struct.unpack(">II", data[16:24]), (1200, 630))
        self.assertGreater(len(data), 100_000)
        self.assertLess(len(data), 2_000_000)

        for declaration in (
            '<link rel="canonical" href="https://lancimoun.github.io/flowproof/" />',
            f'<meta property="og:image" content="{CARD_URL}" />',
            '<meta property="og:image:type" content="image/png" />',
            '<meta property="og:image:width" content="1200" />',
            '<meta property="og:image:height" content="630" />',
            f'<meta property="og:image:alt" content="{CARD_ALT}" />',
            '<meta name="twitter:card" content="summary_large_image" />',
            f'<meta name="twitter:image" content="{CARD_URL}" />',
            f'<meta name="twitter:image:alt" content="{CARD_ALT}" />',
        ):
            self.assertIn(declaration, self.html)

        readme = README.read_text(encoding="utf-8")
        self.assertIn(f"![{CARD_ALT}](docs/flowproof-social-card.png)", readme)

    def test_ci_release_contract_is_supported_recoverable_and_warning_fatal(
        self,
    ) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        runner = RUNNER.read_text(encoding="utf-8")
        requirements = DEV_REQUIREMENTS.read_text(encoding="utf-8")

        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("actions/checkout@v5", workflow)
        self.assertIn("actions/setup-python@v6", workflow)
        self.assertIn("python run_tests.py", workflow)
        self.assertIn("StarletteDeprecationWarning", runner)
        self.assertIn('warnings.filterwarnings("error"', runner)
        self.assertRegex(requirements, r"(?m)^httpx2>=2\.7,<3$")
        self.assertNotRegex(requirements, r"(?m)^httpx(?:[<=>].*)?$")


if __name__ == "__main__":
    unittest.main()
