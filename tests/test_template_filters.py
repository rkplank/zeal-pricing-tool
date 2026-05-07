from zeal.web.templating import configure_template_filters, templates


def test_formula_step_labels_are_human_readable() -> None:
    configure_template_filters()

    label_filter = templates.env.filters["step_label"]

    assert label_filter("ebay_sell_pct") == "eBay sell %"
    assert label_filter("in_mail_buy_ebay") == "In-mail buy, eBay path"
    assert (
        label_filter("ebay_only_due_to_missing_competitor_data")
        == "Using eBay-only recommendation; no competitor data is available"
    )


def test_status_step_test_identifies_explanatory_rows() -> None:
    configure_template_filters()

    status_test = templates.env.tests["status_step"]

    assert status_test("ebay_only_due_to_missing_competitor_data") is True
    assert status_test("no_competitor_analogue") is True
    assert status_test("paypal_sell_costs") is False


def test_display_filters_are_operator_facing() -> None:
    configure_template_filters()

    pct_filter = templates.env.filters["pct"]
    confidence_filter = templates.env.filters["confidence"]
    datetime_filter = templates.env.filters["datetime"]

    assert pct_filter(None) == "No recommendation"
    assert pct_filter(None, "No eBay data") == "No eBay data"
    assert confidence_filter("none") == "No eBay data"
    assert datetime_filter("2026-05-06T22:50:00") == "May 6, 2026, 10:50 PM"
