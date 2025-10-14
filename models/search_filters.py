from pydantic import BaseModel
from typing import Optional, Tuple


class SearchFilters(BaseModel, frozen=True):
    gender_female: Optional[bool] = None  # done
    gender_male: Optional[bool] = None  # done
    state: Optional[str] = None  # done
    interests: Optional[str] = None  # done
    gpa: Optional[str] = None  # done
    free_text: Optional[str] = None
    pets_in_home: Optional[bool] = None  # done
    usahsId: Optional[str] = None  # done
    program_types: Optional[Tuple[str, ...]] = None
    country_of_origin: Optional[str] = None  # done
    grants_options: Optional[Tuple[str, ...]] = None
    adjusted_age: Optional[str] = None  # done
    single_placement: Optional[str] = None  # done
    double_placement: Optional[str] = None  # done
    religiousPractice: Optional[str] = None
    status: Optional[str] = None
    photo_search: Optional[str] = None # done
    early_placement: Optional[str] = None # done
    hasVideo: Optional[bool] = None # done
    statusOptions: Optional[Tuple[str,...]] = None # done
