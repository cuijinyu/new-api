import json
import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pricing_engine


class UsageLogDedupTest(unittest.TestCase):
    def test_seedance_duplicate_settlement_is_not_double_billed(self):
        other = {
            "provider": "service-inference",
            "billing_event": "video_task_settlement",
            "task_id": "mvt-727c320305a7403c",
            "actual_usage": 40594,
            "duration_seconds": 4,
            "unit_scale": 0.000001,
            "group_ratio": 1,
            "price_or_ratio": 5.6,
            "preconsumed_quota": 134400,
            "actual_quota": 113663,
            "quota_delta": -20737,
            "total_tokens": 40594,
        }
        row = {
            "request_id": "20260614174755909552857f8h2UaFY",
            "created_at": 1781430628,
            "user_id": 1,
            "username": "gallon",
            "channel_id": 113,
            "model_name": "dreamina-seedance-2-0-fast-260128",
            "token_name": "测试2",
            "prompt_tokens": 0,
            "completion_tokens": 40594,
            "quota": -20737,
            "content": "",
            "use_time_seconds": 40594,
            "is_stream": False,
            "ip": "127.0.0.1",
            "other": json.dumps(other, ensure_ascii=False),
        }
        df = pd.DataFrame([row, row.copy()])

        recalc = pricing_engine.recalc_from_raw(df)
        self.assertEqual(len(recalc), 1)
        self.assertEqual(float(recalc.iloc[0]["diff_usd"]), 0.0)
        self.assertEqual(int(recalc.iloc[0]["seedance_expected_actual_quota"]), 113663)
        self.assertEqual(int(recalc.iloc[0]["seedance_expected_delta_quota"]), -20737)

        bill = pricing_engine.collapse_postpaid_detail_rows(recalc)
        self.assertEqual(len(bill), 1)
        self.assertEqual(int(bill.iloc[0]["quota"]), 113663)
        self.assertAlmostEqual(float(bill.iloc[0]["billed_usd"]), 0.227326, places=6)


if __name__ == "__main__":
    unittest.main()
