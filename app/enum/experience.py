from enum import StrEnum


class Experience(StrEnum):
    tier_0 = "noExperience"
    tier_1 = "between1And3"
    tier_2 = "between3And6"
    tier_3 = "moreThan6"


class OrderField(StrEnum):
    created_at = "created_at"
    published_at = "published_at"
