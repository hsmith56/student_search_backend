from pydantic import BaseModel, field_validator
from typing import Optional, Tuple


class SearchFilters(BaseModel, frozen=True):
    gender_female: Optional[bool] = None  # done
    gender_male: Optional[bool] = None  # done
    urban_request: Optional[bool] = None # done
    state: Optional[Tuple[str, ...]] = None  # done
    interests: Optional[str] = None  # done
    gpa: Optional[str] = None  # done
    free_text: Optional[str] = None
    pets_in_home: Optional[str] = None  # done
    usahsId: Optional[str] = None  # done
    program_types: Optional[Tuple[str, ...]] = None
    country_of_origin: Optional[Tuple[str, ...]] = None  # done
    grants_options: Optional[Tuple[str, ...]] = None
    adjusted_age: Optional[str] = None  # done
    single_placement: Optional[str] = None  # done
    double_placement: Optional[str] = None  # done
    religiousPractice: Optional[str] = None
    status: Optional[str] = None
    photo_search: Optional[str] = None  # done
    early_placement: Optional[str] = None  # done
    hasVideo: Optional[bool] = None  # done
    statusOptions: Optional[Tuple[str, ...]] = None  # done

    @field_validator("state", mode="before")
    @classmethod
    def normalize_state(cls, value: object) -> Optional[Tuple[str, ...]]:
        if value is None:
            return None

        if isinstance(value, str):
            normalized = value.strip()
            return (normalized,) if normalized else tuple()

        if isinstance(value, (list, tuple, set)):
            deduped: list[str] = []
            for item in value:
                if not isinstance(item, str):
                    continue
                normalized = item.strip()
                if not normalized:
                    continue
                if normalized not in deduped:
                    deduped.append(normalized)
            return tuple(deduped)

        return tuple()
