"""Labor-law calculation engine. Pure Python: no database or web imports (see tests/test_purity.py).

Inputs: punches, the day's resolved shift, the day type, approved leaves/missions/overtime and
the Labor Rule Set. Output: a DailyResult. See daily.calculate_day.
"""
