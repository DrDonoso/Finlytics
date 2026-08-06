"""Tests for the Euribor index feed (parsing and resolution).

Network access is never exercised here — only the pure parsing and lookup
logic, fed with a sample of the real ECB ``csvdata`` payload.
"""

from datetime import date
from decimal import Decimal as D

from finlytics.mortgage.euribor import make_resolver, parse_ecb_csv

# Trimmed to the columns the parser actually reads; the real payload has ~40.
SAMPLE_CSV = """KEY,FREQ,TIME_PERIOD,OBS_VALUE,OBS_STATUS,TITLE
FM.M.U2.EUR.RT.MM.EURIBOR1YD_.HSTA,M,2024-01,3.6092273,A,Euribor 1-year
FM.M.U2.EUR.RT.MM.EURIBOR1YD_.HSTA,M,2024-02,3.6712,A,Euribor 1-year
FM.M.U2.EUR.RT.MM.EURIBOR1YD_.HSTA,M,2024-03,3.7182,A,Euribor 1-year
"""


class TestParseEcbCsv:
    def test_extracts_every_observation(self):
        assert len(parse_ecb_csv(SAMPLE_CSV)) == 3

    def test_maps_period_to_first_day_of_month(self):
        assert parse_ecb_csv(SAMPLE_CSV)[0][0] == date(2024, 1, 1)

    def test_keeps_full_decimal_precision(self):
        assert parse_ecb_csv(SAMPLE_CSV)[0][1] == D("3.6092273")

    def test_returns_rows_sorted_by_period(self):
        periods = [p for p, _ in parse_ecb_csv(SAMPLE_CSV)]
        assert periods == sorted(periods)

    def test_skips_rows_with_an_empty_value(self):
        csv = SAMPLE_CSV + "FM.X,M,2024-04,,A,Euribor 1-year\n"
        assert len(parse_ecb_csv(csv)) == 3

    def test_skips_rows_with_a_malformed_period(self):
        csv = SAMPLE_CSV + "FM.X,M,not-a-date,2.5,A,Euribor 1-year\n"
        assert len(parse_ecb_csv(csv)) == 3

    def test_skips_rows_with_a_non_numeric_value(self):
        csv = SAMPLE_CSV + "FM.X,M,2024-04,N/A,A,Euribor 1-year\n"
        assert len(parse_ecb_csv(csv)) == 3

    def test_empty_payload_yields_no_rows(self):
        assert parse_ecb_csv("") == []


class TestResolver:
    def _resolver(self):
        return make_resolver(dict(parse_ecb_csv(SAMPLE_CSV)))

    def test_published_month_is_exact_and_not_projected(self):
        rate, projected = self._resolver()("euribor_12m", date(2024, 2, 1))
        assert rate == D("3.6712")
        assert projected is False

    def test_ignores_the_day_within_the_month(self):
        assert self._resolver()("euribor_12m", date(2024, 2, 27))[0] == D("3.6712")

    def test_future_month_falls_back_to_the_latest_known(self):
        rate, projected = self._resolver()("euribor_12m", date(2030, 1, 1))
        assert rate == D("3.7182")
        assert projected is True

    def test_month_before_the_series_uses_the_earliest_known(self):
        rate, projected = self._resolver()("euribor_12m", date(1990, 1, 1))
        assert rate == D("3.6092273")
        assert projected is True

    def test_empty_series_degrades_to_zero_and_projected(self):
        rate, projected = make_resolver({})("euribor_12m", date(2024, 1, 1))
        assert rate == D("0")
        assert projected is True
