def blend_values(ebay_value: float, competitor_value: float, ebay_weight: float) -> float:
    if ebay_weight < 0.0 or ebay_weight > 1.0:
        raise ValueError("ebay_weight must be between 0.0 and 1.0")
    return (ebay_weight * ebay_value) + ((1.0 - ebay_weight) * competitor_value)
