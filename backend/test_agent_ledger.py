import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from backend import agent


class AgentLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.recommendations = self.root / "agent_recommendations.jsonl"
        self.outcomes = self.root / "agent_outcomes.jsonl"
        self.journal = self.root / "agent_journal.csv"

    def tearDown(self):
        self.temp_dir.cleanup()

    @staticmethod
    def close_history():
        dates = pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07"])
        return pd.DataFrame(
            {"AAA.WA": [100.0, 110.0, 121.0], "BBB.WA": [50.0, 55.0, 55.0]},
            index=dates,
        )

    @staticmethod
    def stock():
        return {
            "ticker": "AAA.WA", "price": 111.0, "last_updated": "2026-01-07T10:00:00",
            "pe": 9.0, "pbv": 1.2, "roe": 0.2, "div_yield": 0.04,
            "debt_to_equity": 0.3,
        }

    def test_unique_ids_and_same_day_ticker_signals_are_appended(self):
        first = {"ticker": "AAA.WA", "action": "BUY", "score": 70.0,
                 "momentum": 0.1, "fundamental": 60, "reason": "first"}
        second = {"ticker": "AAA.WA", "action": "SELL", "score": 10.0,
                  "momentum": -0.1, "fundamental": 20, "reason": "second"}
        with patch.object(agent, "RECOMMENDATIONS", self.recommendations):
            self.assertEqual(agent.log_agent_signals([first], self.close_history(), [self.stock()]), 1)
            first_line = self.recommendations.read_text(encoding="utf-8").splitlines()[0]
            self.assertEqual(agent.log_agent_signals([second], self.close_history(), [self.stock()]), 1)

        rows = [json.loads(line) for line in self.recommendations.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(rows), 2)
        self.assertNotEqual(rows[0]["signal_id"], rows[1]["signal_id"])
        self.assertEqual([row["action"] for row in rows], ["BUY", "SELL"])
        self.assertEqual(self.recommendations.read_text(encoding="utf-8").splitlines()[0], first_line)
        self.assertEqual(rows[0]["price_reference"]["value"], 111.0)
        self.assertEqual(rows[0]["price_reference"]["source"], "agent stock input:price")
        self.assertEqual(rows[0]["momentum_price_reference"]["value"], 121.0)
        self.assertEqual(rows[0]["momentum_price_reference"]["source"], "data/daily_prices.csv:close")
        self.assertEqual(rows[0]["fundamental_snapshot"]["score_components"]["pe"]["points"], 25)
        self.assertTrue(rows[0]["rules_version"])

    def test_legacy_entries_are_copied_once_without_changing_csv(self):
        original = "date,ticker,action,score,momentum\n2026-01-05,AAA.WA,BUY,70.0,0.1\n"
        self.journal.write_text(original, encoding="utf-8")
        with patch.object(agent, "JOURNAL", self.journal), \
             patch.object(agent, "RECOMMENDATIONS", self.recommendations):
            self.assertEqual(agent.migrate_legacy_agent_journal(), 1)
            self.assertEqual(agent.migrate_legacy_agent_journal(), 0)

        self.assertEqual(self.journal.read_text(encoding="utf-8"), original)
        migrated = json.loads(self.recommendations.read_text(encoding="utf-8"))
        self.assertTrue(migrated["signal_id"].startswith("legacy-"))
        self.assertEqual(migrated["rules_version"], "unknown_legacy")
        self.assertIsNone(migrated["price_reference"]["value"])

    def test_existing_rule_score_and_thresholds_are_unchanged(self):
        stock = {"ticker": "AAA.WA", "pe": 9.0, "roe": 0.2,
                 "div_yield": 0.04, "debt_to_equity": 0.3}
        scored = agent.score_stock(stock, None)
        self.assertEqual(agent.BUY_THRESHOLD, 60)
        self.assertEqual(agent.SELL_THRESHOLD, 20)
        self.assertEqual(scored["fundamental"], 75)
        self.assertEqual(scored["score"], 75.0)
        self.assertEqual(agent.calc_fundamental_score(stock), 75)

    def test_each_generated_recommendation_gets_a_unique_id_and_timestamp(self):
        stock = {"ticker": "AAA.WA", "pe": 9.0, "roe": 0.2,
                 "div_yield": 0.04, "debt_to_equity": 0.3}
        first = agent.generate_signals([stock], None)[0]
        second = agent.generate_signals([stock], None)[0]
        self.assertNotEqual(first["signal_id"], second["signal_id"])
        self.assertEqual(first["action"], "BUY")
        self.assertIsNotNone(pd.Timestamp(first["signal_at"]).tzinfo)

    def test_outcomes_reference_their_own_signal_and_are_append_only(self):
        signals = [
            {"signal_id": "signal-one", "ticker": "AAA.WA", "action": "BUY",
             "signal_date": "2026-01-05"},
            {"signal_id": "signal-two", "ticker": "AAA.WA", "action": "SELL",
             "signal_date": "2026-01-06"},
        ]
        self.recommendations.write_text(
            "".join(json.dumps(row) + "\n" for row in signals), encoding="utf-8"
        )
        with patch.object(agent, "RECOMMENDATIONS", self.recommendations), \
             patch.object(agent, "OUTCOMES", self.outcomes), \
             patch.object(agent, "HORIZONS", (1,)):
            self.assertEqual(agent.persist_matured_agent_outcomes(self.close_history()), 2)
            saved_lines = self.outcomes.read_text(encoding="utf-8").splitlines()
            self.assertEqual(agent.persist_matured_agent_outcomes(self.close_history()), 0)

        results = {row["signal_id"]: row for row in map(json.loads, saved_lines)}
        self.assertEqual(set(results), {"signal-one", "signal-two"})
        self.assertEqual(results["signal-one"]["entry_price_used"], 100.0)
        self.assertEqual(results["signal-two"]["entry_price_used"], 110.0)
        self.assertEqual(results["signal-one"]["outcome_id"], "signal-one:1")
        self.assertEqual(len(self.outcomes.read_text(encoding="utf-8").splitlines()), 2)


if __name__ == "__main__":
    unittest.main()
