"""Pure AST-extracted helpers: never import/run trainer or status entry points."""
import ast
import math
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "train" / "train_navigator_r2.py"


def helpers():
    tree = ast.parse(SOURCE.read_text())
    names = {"finite_training_loss", "status_receipt"}
    # Only literal constants and the two inspected pure helper bodies execute.
    selected = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            try:
                ast.literal_eval(node.value)
            except (ValueError, TypeError):
                continue
            selected.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in names:
            selected.append(node)
    ns = {"math": math, "Any": object}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(SOURCE), "exec"), ns)
    return ns


class TrainingLossLabelTests(unittest.TestCase):
    def test_invalid_losses_are_unavailable(self):
        ns = helpers()
        for value in [None, "", "UNAVAILABLE", "nan", "inf", "-inf", "1e9999",
                      float("nan"), float("inf"), -float("inf"), True, False, [], {}, "oops"]:
            with self.subTest(value=value):
                r = ns["status_receipt"](hub="test", dataset_sha="fixture", training_loss=value)
                self.assertEqual(r["train_loss_label"], "UNAVAILABLE")
                self.assertIsNone(r["finalTrainLoss"])

    def test_finite_values_preserved(self):
        ns = helpers()
        for value in ["0.0000", "0.4397", "-0.1", "1e-4", 0, 0.5, -1.0]:
            with self.subTest(value=value):
                r = ns["status_receipt"](hub="test", dataset_sha="fixture", training_loss=value)
                self.assertEqual(r["train_loss_label"], "MEASURED")
                self.assertEqual(r["finalTrainLoss"], value)
                self.assertEqual(r["evals"], "none-this-run")
                self.assertFalse(r["publication_eligible"])
                self.assertFalse(r["autonomy_eligible"])
                self.assertIsNone(r["computed_at"])

    def test_train_output_uses_finite_guard_and_label(self):
        source = SOURCE.read_text()
        self.assertIn('final_loss = f"{loss:.4f}" if finite_training_loss(loss) else None', source)
        self.assertIn('train_loss {loss_label} {final_loss}', source)
        self.assertNotIn('train_loss MEASURED {final_loss}', source)


if __name__ == "__main__":
    unittest.main()
