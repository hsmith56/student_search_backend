from typing import Optional
from pydantic import BaseModel


class BasicStudent(BaseModel):
    first_name: str
    app_id: int
    pax_id: int
    country: str
    gpa: str
    english_score: str
    applying_to_grade: int
    usahsid: str
    program_type: str
    adjusted_age: int
    selected_interests: list[str]  # use for embeddings
    urban_request: str
    placement_status: str
    gender_desc: str  # use for embeddings


class FullStudent(BasicStudent):
    id: int
    current_grade: int
    status: str
    states: set[str]
    early_placement: Optional[bool] = False
    single_placement: bool
    double_placement: bool
    free_text_interests: list[str]
    family_description: str  # use for embeddings
    favorite_subjects: str  # use for embeddings
    photo_comments: str  # use for embeddings
    religion: str  # use for embeddings
    allergy_comments: str  # use for embeddings
    dietary_restrictions: str  # use for embeddings
    religious_frequency: int
    intro_message: str  # use for embeddings
    message_to_host_family: str  # use for embeddings
    message_from_natural_family: str  # use for embeddings
    media_link: str
    health_comments: list[str]  # use for embeddings
    live_with_pets: Optional[bool]
    local_coordinator: Optional[str] = ""
