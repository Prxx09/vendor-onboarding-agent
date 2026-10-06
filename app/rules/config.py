from dataclasses import dataclass, field


@dataclass
class RulesConfig:
    """Central deterministic rule thresholds; thresholds are inclusive unless stated otherwise."""

    name_similarity_threshold: int = 90
    address_similarity_threshold: int = 85
    holder_name_similarity_threshold: int = 85
    sanctions_match_threshold: int = 90
    low_confidence_threshold: float = 0.7
    high_value_threshold: float = 100_000
    high_risk_countries: list[str] = field(default_factory=list)
    bank_letter_max_age_days: int = 180
