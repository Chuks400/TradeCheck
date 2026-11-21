"""Check that browser JavaScript references existing HTML element IDs."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class UIChecks(unittest.TestCase):
    def test_javascript_refs_have_html_elements(self):
        html = (ROOT / "web/index.html").read_text(encoding="utf-8")
        js = (ROOT / "web/app.js").read_text(encoding="utf-8")
        ids = re.findall(r'id="([^"]+)"', html)
        self.assertEqual(len(ids), len(set(ids)), "Duplicate HTML IDs")
        refs = set(re.findall(r"\$\('([^']+)'\)", js))
        self.assertFalse(refs - set(ids), "Missing IDs: " + ", ".join(sorted(refs - set(ids))))

    def test_llm_controls_present(self):
        html = (ROOT / "web/index.html").read_text(encoding="utf-8")
        for required in ('id="useLlm"', 'id="llmModel"', 'id="llmStatus"'):
            self.assertIn(required, html)


if __name__ == "__main__":
    unittest.main()
