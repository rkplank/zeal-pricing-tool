import pytest
from pydantic import ValidationError

from zeal.models.merchant import MerchantConfig, MerchantRecord

# --- Valid instantiation tests ---

def test_mastercard_normal_merchant() -> None:
    # Mastercard (row 3 in PricingSheet): T24 tier, all channels active.
    # Values derived from spreadsheet_recon.md §2 worked example:
    # B3=1.05, ebay_diff=0.045 → online_sell=1.005; in_mail=0.895; in_store=0.647; elec=0.815
    m = MerchantConfig(
        merchant_id="mastercard",
        display_name="Mastercard",
        tier="T24",
        in_store_margin=0.25,
        in_mail_margin=0.03,
        e_bonus=0.08,
        ebay_differential=0.045,
        in_store_eligible=True,
        in_mail_eligible=True,
        electronic_eligible=True,
        merch_credit_variant=False,
    )
    assert m.merchant_id == "mastercard"
    assert m.tier == "T24"
    assert m.e_bonus == 0.08
    assert m.online_sell_override is None
    assert m.electronic_buy_override is None
    assert m.notes is None
    assert m.ebay_weight == 1.0
    assert m.risk_status == "normal"
    assert m.risk_note is None


def test_pattern_a_merchant_with_online_sell_override() -> None:
    # Andiamo (row 250): local NC-tier merchant, no eBay data, hardcoded online_sell.
    # online_sell_override is set; downstream channels compute from it.
    m = MerchantConfig(
        merchant_id="andiamo",
        display_name="Andiamo",
        tier="NC",
        in_store_margin=0.30,
        in_mail_margin=0.15,
        e_bonus=0.17,
        ebay_differential=0.025,
        in_store_eligible=True,
        in_mail_eligible=True,
        electronic_eligible=True,
        merch_credit_variant=False,
        online_sell_override=0.75,
    )
    assert m.online_sell_override == 0.75
    assert m.electronic_buy_override is None
    assert m.tier == "NC"


def test_home_depot_estore_credit_with_electronic_buy_override() -> None:
    # Home Depot eStore Credit (row 14, spreadsheet_recon.md §7):
    # in_mail and in_store ineligible; electronic only with hardcoded payout.
    m = MerchantConfig(
        merchant_id="home_depot_estore_credit",
        display_name="Home Depot eStore Credit",
        tier="Z",
        in_store_margin=0.29,
        in_mail_margin=0.11,
        e_bonus=None,
        ebay_differential=0.025,
        in_store_eligible=False,
        in_mail_eligible=False,
        electronic_eligible=True,
        merch_credit_variant=True,
        electronic_buy_override=0.65,
    )
    assert m.in_store_eligible is False
    assert m.in_mail_eligible is False
    assert m.electronic_eligible is True
    assert m.electronic_buy_override == 0.65
    assert m.merch_credit_variant is True
    assert m.e_bonus is None


def test_merchant_record_extends_config() -> None:
    rec = MerchantRecord(
        merchant_id="mastercard",
        display_name="Mastercard",
        tier="T24",
        in_store_margin=0.25,
        in_mail_margin=0.03,
        e_bonus=0.08,
        ebay_differential=0.045,
        in_store_eligible=True,
        in_mail_eligible=True,
        electronic_eligible=True,
        merch_credit_variant=False,
        inclusion_regex=r"mastercard",
        exclusion_regex=None,
        is_active=True,
        created_at="2026-05-02T00:00:00",
        updated_at="2026-05-02T00:00:00",
    )
    assert rec.inclusion_regex == r"mastercard"
    assert rec.exclusion_regex is None
    assert rec.is_active is True


# --- Validation error tests ---

def test_missing_required_field_raises() -> None:
    with pytest.raises(ValidationError):
        MerchantConfig(  # type: ignore[call-arg]
            # merchant_id omitted
            display_name="Test",
            tier="T24",
            in_store_margin=0.25,
            in_mail_margin=0.03,
            ebay_differential=0.045,
            in_store_eligible=True,
            in_mail_eligible=True,
            electronic_eligible=True,
            merch_credit_variant=False,
        )


def test_invalid_tier_raises() -> None:
    with pytest.raises(ValidationError):
        MerchantConfig(
            merchant_id="test",
            display_name="Test",
            tier="INVALID",  # type: ignore[arg-type]
            in_store_margin=0.25,
            in_mail_margin=0.03,
            ebay_differential=0.045,
            in_store_eligible=True,
            in_mail_eligible=True,
            electronic_eligible=True,
            merch_credit_variant=False,
        )


def test_invalid_ebay_weight_raises() -> None:
    with pytest.raises(ValidationError):
        MerchantConfig(
            merchant_id="test",
            display_name="Test",
            tier="C",
            in_store_margin=0.25,
            in_mail_margin=0.03,
            ebay_differential=0.045,
            in_store_eligible=True,
            in_mail_eligible=True,
            electronic_eligible=True,
            merch_credit_variant=False,
            ebay_weight=1.1,
        )
