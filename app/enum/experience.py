from enum import Enum


class Experience(str, Enum):
    tier_0 = "noExperience"
    tier_1 = "between1And3"
    tier_2 = "between3And6"
    tier_3 = "moreThan6"
