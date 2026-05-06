from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from historical_spreadsheet_recon import (
    CellValue,
    detect_column_map,
    extract_rows,
    find_header_row,
    normalize_label,
    parse_percent,
    used_range,
)


class FakeSheet:
    def __init__(self, name: str, rows: list[list[object]]) -> None:
        self.name = name
        self._rows = rows
        self.nrows = len(rows)
        self.ncols = max(len(row) for row in rows)

    def cell(self, row: int, col: int) -> CellValue:
        if row >= self.nrows or col >= len(self._rows[row]):
            return CellValue(None)
        return CellValue(self._rows[row][col])


def test_normalize_label_collapses_punctuation_and_space() -> None:
    assert normalize_label(" CC Sell\n") == "cc sell"
    assert normalize_label("Pricing Tier") == "pricing tier"


def test_parse_percent_normalizes_numbers_and_strings() -> None:
    assert parse_percent(0.875) == 0.875
    assert parse_percent("87.5%") == 0.875
    assert parse_percent("87.5") == 0.875
    assert parse_percent("No Data") is None
    assert parse_percent("#VALUE!") is None


def test_detect_column_map_finds_competitor_columns() -> None:
    detected = detect_column_map(["Merchant", "CardCash Buy", "CardCash Sell", "Raise Sell"])
    assert detected == {
        "merchant_name": 0,
        "cardcash_buy": 1,
        "cardcash_sell": 2,
        "raise_sell": 3,
    }


def test_find_header_row_handles_split_pricing_sheet_header() -> None:
    sheet = FakeSheet(
        "PricingSheet",
        [
            ["", "eBay Sell", "", "Buy", "Buy", "Buy", "Online Sell", ""],
            ["Merchant", "", "In-Mail", "Electronic", "In-Store", "", "Pricing Tier", "CC Buy"],
            ["Mastercard", 1.05, 0.895, 0.815, 0.647, 1.005, "T24", 0.91],
        ],
    )

    header_row, column_map = find_header_row(sheet)

    assert header_row == 1
    assert column_map["merchant_name"] == 0
    assert column_map["ebay_sell"] == 1
    assert column_map["online_sell"] == 5
    assert column_map["cardcash_buy"] == 7


def test_extract_rows_normalizes_pricing_sheet_values() -> None:
    sheet = FakeSheet(
        "PricingSheet",
        [
            ["", "eBay Sell", "", "Buy", "Buy", "Buy", "Online Sell"],
            ["Merchant", "", "In-Mail", "Electronic", "In-Store", "", "Pricing Tier"],
            ["Mastercard", 1.05, 0.895, 0.815, 0.647, 1.005, "T24"],
            ["LOCAL", "", "", "", "", "", ""],
            ["Andiamo", "N/A", 0.45, "No", 0.32, 0.65, "NC"],
        ],
    )
    header_row, column_map = find_header_row(sheet)

    rows = extract_rows(sheet, Path("GiftCardPricingData_2025.xls"), "xls", header_row, column_map)

    assert [row.merchant_id for row in rows] == ["mastercard", "andiamo"]
    assert rows[0].ebay_sell == 1.05
    assert rows[0].online_sell == 1.005
    assert rows[1].electronic_buy is None
    assert rows[1].tier == "NC"


def test_used_range_ignores_empty_trailing_cells() -> None:
    sheet = FakeSheet("Sheet1", [[None, None, None], [None, "x", None], [None, None, "y"]])

    result = used_range(sheet)

    assert result.display == "R2C2:R3C3"
