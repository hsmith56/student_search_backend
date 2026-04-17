import logging
from functools import lru_cache
from typing import Callable, Optional, Sequence, Final

from models.search_filters import SearchFilters
from models.student import FullStudent
from rapidfuzz import fuzz, utils

logger = logging.getLogger(__name__)
FilterStep = Callable[[list[FullStudent], SearchFilters], list[FullStudent]]


PHOTO_MATCH_THRESHOLD: Final[int] = 86
FREE_TEXT_RATIO_THRESHOLD: Final[int] = 88


def _normalized_tuple_values(values: Optional[tuple[str, ...]]) -> list[str]:
    if values is None:
        return []
    return [value.strip().lower() for value in values if isinstance(value, str) and value.strip()]


def _filter_status_options(
    students: list[FullStudent], filters: SearchFilters
) -> list[FullStudent]:
    status_options = _normalized_tuple_values(filters.statusOptions)
    if not status_options or "all" in status_options:
        return students

    return [
        student
        for student in students
        if any(option in student.placement_status.lower() for option in status_options)
    ]


def _filter_urban_request(students: list[FullStudent], filters: SearchFilters) -> list[FullStudent]:
    if filters.urban_request is False:
        return students
    
    return [student for student in students if "Urban" in student.urban_request]


def _filter_gender(students: list[FullStudent], filters: SearchFilters) -> list[FullStudent]:
    if filters.gender_female is None or filters.gender_male is None:
        return students

    if filters.gender_female is True and filters.gender_male is True:
        return students
    if filters.gender_female is True:
        return [student for student in students if student.gender_desc.lower() == "female"]
    if filters.gender_male is True:
        return [student for student in students if student.gender_desc.lower() == "male"]
    return students


def _filter_state(students: list[FullStudent], filters: SearchFilters) -> list[FullStudent]:
    if filters.state is None:
        return students

    state_filters = _normalized_tuple_values(filters.state)
    state_filters_set = set(state_filters)
    specific_states = {
        state for state in state_filters_set if state not in {"all", "no_pref", "state_only"}
    }

    if state_filters == ["all"]:
        return students
    if state_filters == ["no_pref"]:
        return [student for student in students if len(student.states) == 0]
    if state_filters == ["state_only"]:
        return [student for student in students if len(student.states) != 0]

    include_no_pref = "no_pref" in state_filters_set
    if include_no_pref and specific_states:
        return [
            student
            for student in students
            if len(student.states) == 0
            or any(state.lower() in specific_states for state in student.states)
        ]
    if include_no_pref:
        return [student for student in students if len(student.states) == 0]
    return [student for student in students if any(state.lower() in specific_states for state in student.states)]


def _filter_interests(students: list[FullStudent], filters: SearchFilters) -> list[FullStudent]:
    interest_filters = _normalized_tuple_values(filters.interests)
    if interest_filters is None or interest_filters == ["all"]:
        return students

    return [student for student in students if len(set(interest_filters) & set([n_int.lower() for n_int in student.selected_interests])) >= 1]


def _filter_gpa(students: list[FullStudent], filters: SearchFilters) -> list[FullStudent]:
    if filters.gpa is None or filters.gpa == "all":
        return students

    try:
        gpa_value = float(filters.gpa)
    except ValueError:
        return students

    return [student for student in students if student.gpa and float(student.gpa) >= gpa_value]


def _filter_pets_in_home(students: list[FullStudent], filters: SearchFilters) -> list[FullStudent]:
    if filters.pets_in_home is None or filters.pets_in_home == "all":
        return students

    mapping = {"yes": True, "no": False}
    target = mapping.get(filters.pets_in_home)
    if target is None:
        return students
    return [student for student in students if student.live_with_pets is target]


def _filter_usahsid(students: list[FullStudent], filters: SearchFilters) -> list[FullStudent]:
    if not filters.usahsId:
        return students
    query = filters.usahsId.lower()
    return [student for student in students if query in student.usahsid.lower()]


def _filter_country_of_origin(students: list[FullStudent], filters: SearchFilters) -> list[FullStudent]:
    countries = _normalized_tuple_values(filters.country_of_origin)
    if not countries or "all" in countries:
        return students
    country_set = set(countries)
    return [student for student in students if student.country.lower() in country_set]


def _filter_adjusted_age(students: list[FullStudent], filters: SearchFilters) -> list[FullStudent]:
    if filters.adjusted_age is None or filters.adjusted_age == "all":
        return students

    try:
        age_value = int(filters.adjusted_age)
    except ValueError:
        return students

    return [
        student for student in students if student.adjusted_age and student.adjusted_age >= age_value
    ]


def _filter_single_placement(students: list[FullStudent], filters: SearchFilters) -> list[FullStudent]:
    if filters.single_placement is None or filters.single_placement == "all":
        return students

    value = filters.single_placement.lower()
    if value == "yes":
        return [student for student in students if student.single_placement is True]
    if value == "no":
        return [student for student in students if student.single_placement is False]
    return students


def _filter_double_placement(students: list[FullStudent], filters: SearchFilters) -> list[FullStudent]:
    if filters.double_placement is None or filters.double_placement == "all":
        return students

    value = filters.double_placement.lower()
    if value == "yes":
        return [student for student in students if student.double_placement is True]
    if value == "no":
        return [student for student in students if student.double_placement is False]
    return students


def _filter_program_types(students: list[FullStudent], filters: SearchFilters) -> list[FullStudent]:
    if filters.program_types is None or not filters.program_types:
        return students

    mapping = {
        "10-month-aug": "August 10",
        "5-month-aug": "August 5",
        "10-month-jan": "January 10",
        "5-month-jan": "January 5",
    }
    program_types = [mapping[program_type] for program_type in filters.program_types]
    return [student for student in students if any(program in student.program_type for program in program_types)]


def _filter_early_placement(students: list[FullStudent], filters: SearchFilters) -> list[FullStudent]:
    if filters.early_placement is None or filters.early_placement == "all":
        return students

    if filters.early_placement.lower() == "yes":
        return [student for student in students if "EP" in student.usahsid.upper()]
    return [student for student in students if "EP" not in student.usahsid.upper()]


def _filter_has_video(students: list[FullStudent], filters: SearchFilters) -> list[FullStudent]:
    if filters.hasVideo is None or filters.hasVideo is False:
        return students
    return [student for student in students if student.media_link != ""]


def _filter_religious_practice(students: list[FullStudent], filters: SearchFilters) -> list[FullStudent]:
    if filters.religiousPractice is None or filters.religiousPractice == "all":
        return students

    mapping = {"none": 0, "some": 1, "often": 2}
    return [
        student for student in students if student.religious_frequency == mapping[filters.religiousPractice]
    ]


def _filter_grants_options(students: list[FullStudent], filters: SearchFilters) -> list[FullStudent]:
    if filters.grants_options is None or len(filters.grants_options) == 0:
        return students

    if "grant" in filters.grants_options:
        grant_prefixes = {"CBE", "CBX", "FAO", "FLX", "YES", "CBG"}
        return [student for student in students if student.usahsid.upper()[0:3] in grant_prefixes]

    grants_set = set(filters.grants_options)
    return [student for student in students if student.usahsid.lower()[0:3] in grants_set]


def _filter_photo_search(students: list[FullStudent], filters: SearchFilters) -> list[FullStudent]:
    if filters.photo_search is None or filters.photo_search == "":
        return students

    return [
        student
        for student in students
        if fuzz.partial_ratio(
            filters.photo_search, student.photo_comments, processor=utils.default_process
        )
        >= PHOTO_MATCH_THRESHOLD
    ]


def _normalize_free_text_value(value: str | None) -> str:
    processed = utils.default_process(value if value is not None else "")
    return processed or ""


@lru_cache(maxsize=2048)
def _prepare_free_text_fields_cached(
    first_name: str,
    photo_comments: str,
    religion: str,
    allergy_comments: str,
    dietary_restrictions: str,
    health_comments: tuple[str, ...],
    favorite_subjects: str,
    selected_interests: tuple[str, ...],
    free_text_interests: tuple[str, ...],
    intro_message: str,
    message_to_host_family: str,
    message_from_natural_family: str,
) -> tuple[str, ...]:
    return (
        _normalize_free_text_value(first_name),
        _normalize_free_text_value(photo_comments),
        _normalize_free_text_value(religion),
        _normalize_free_text_value(allergy_comments),
        _normalize_free_text_value(dietary_restrictions),
        _normalize_free_text_value(" ".join(w for w in health_comments)),
        _normalize_free_text_value(" ".join(w for w in favorite_subjects)),
        _normalize_free_text_value(" ".join(w for w in selected_interests)),
        _normalize_free_text_value(" ".join(w for w in free_text_interests)),
        _normalize_free_text_value(intro_message),
        _normalize_free_text_value(message_to_host_family),
        _normalize_free_text_value(message_from_natural_family),
    )


def _prepare_free_text_fields(student: FullStudent) -> tuple[str, ...]:
    return _prepare_free_text_fields_cached(
        student.first_name,
        student.photo_comments,
        student.religion,
        student.allergy_comments,
        student.dietary_restrictions,
        tuple(student.health_comments),
        student.favorite_subjects,
        tuple(student.selected_interests),
        tuple(student.free_text_interests),
        student.intro_message,
        student.message_to_host_family,
        student.message_from_natural_family,
    )


def _parse_free_text_query(search_query: str) -> list[tuple[str, ...]]:
    normalized_query = search_query.strip()
    if not normalized_query:
        return []

    clauses: list[tuple[str, ...]] = []
    for and_clause in normalized_query.split("|"):
        normalized_terms = tuple(
            normalized
            for normalized in (
                _normalize_free_text_value(term.strip())
                for term in and_clause.split("&")
            )
            if normalized
        )
        if normalized_terms:
            clauses.append(normalized_terms)
    return clauses


def _matches_free_text_term(search_query: str, prepared_fields: tuple[str, ...]) -> bool:
    (
        first_name,
        photo_comments,
        religion,
        allergy_comments,
        dietary_restrictions,
        health_comments,
        favorite_subjects,
        selected_interests,
        free_text_interests,
        intro_message,
        message_to_host_family,
        message_from_natural_family,
    ) = prepared_fields

    if (
        fuzz.ratio(search_query, first_name, processor=None)
        >= FREE_TEXT_RATIO_THRESHOLD
    ):
        return True
    if (
        fuzz.partial_ratio(search_query, photo_comments, processor=None)
        >= FREE_TEXT_RATIO_THRESHOLD
    ):
        return True
    if (
        fuzz.ratio(search_query, religion, processor=None)
        >= FREE_TEXT_RATIO_THRESHOLD
    ):
        return True
    if (
        fuzz.partial_ratio(search_query, allergy_comments, processor=None)
        >= FREE_TEXT_RATIO_THRESHOLD
    ):
        return True
    if (
        fuzz.partial_ratio(search_query, dietary_restrictions, processor=None)
        >= FREE_TEXT_RATIO_THRESHOLD
    ):
        return True
    if (
        fuzz.partial_ratio(search_query, health_comments, processor=None)
        >= FREE_TEXT_RATIO_THRESHOLD
    ):
        return True
    if (
        fuzz.partial_ratio(search_query, favorite_subjects, processor=None)
        >= FREE_TEXT_RATIO_THRESHOLD
    ):
        return True
    if (
        fuzz.partial_ratio(search_query, selected_interests, processor=None)
        >= FREE_TEXT_RATIO_THRESHOLD
    ):
        return True
    if (
        fuzz.partial_ratio(search_query, free_text_interests, processor=None)
        >= FREE_TEXT_RATIO_THRESHOLD
    ):
        return True
    if (
        fuzz.partial_ratio(search_query, intro_message, processor=None)
        >= FREE_TEXT_RATIO_THRESHOLD
    ):
        return True
    if (
        fuzz.partial_ratio(search_query, message_to_host_family, processor=None)
        >= FREE_TEXT_RATIO_THRESHOLD
    ):
        return True
    if (
        fuzz.partial_ratio(search_query, message_from_natural_family, processor=None)
        >= FREE_TEXT_RATIO_THRESHOLD
    ):
        return True
    return False


def _matches_free_text_clauses(
    clauses: list[tuple[str, ...]], student: FullStudent
) -> bool:
    prepared_fields = _prepare_free_text_fields(student)
    return any(
        all(_matches_free_text_term(term, prepared_fields) for term in and_terms)
        for and_terms in clauses
    )


def _matches_free_text(search_query: str, student: FullStudent) -> bool:
    clauses = _parse_free_text_query(search_query)
    if not clauses:
        return False
    return _matches_free_text_clauses(clauses, student)


def _filter_free_text(students: list[FullStudent], filters: SearchFilters) -> list[FullStudent]:
    if filters.free_text is None or filters.free_text == "":
        return students

    clauses = _parse_free_text_query(filters.free_text)
    if not clauses:
        return students

    return [student for student in students if _matches_free_text_clauses(clauses, student)]


FilterSpec = tuple[str, FilterStep]

_FILTER_STEPS: Final[Sequence[FilterSpec]] = (
    ("status_options", _filter_status_options),
    ("gender", _filter_gender),
    ("urban", _filter_urban_request),
    ("state", _filter_state),
    ("interests", _filter_interests),
    ("gpa", _filter_gpa),
    ("pets_in_home", _filter_pets_in_home),
    ("usahsid", _filter_usahsid),
    ("country_of_origin", _filter_country_of_origin),
    ("adjusted_age", _filter_adjusted_age),
    ("single_placement", _filter_single_placement),
    ("double_placement", _filter_double_placement),
    ("program_types", _filter_program_types),
    ("early_placement", _filter_early_placement),
    ("has_video", _filter_has_video),
    ("religious_practice", _filter_religious_practice),
    ("grants_options", _filter_grants_options),
    ("photo_search", _filter_photo_search),
    ("free_text", _filter_free_text),
)

_FILTER_LOOKUP = {name: fn for name, fn in _FILTER_STEPS}


def _apply_filters(students: list[FullStudent], filters: SearchFilters) -> list[FullStudent]:
    res = students
    for name, step in _FILTER_STEPS:
        before_count = len(res)
        res = step(res, filters)
        if before_count != len(res):
            logger.debug("%s count=%s", name, len(res))
    return res


def apply_single_filter(students: list[FullStudent], filters: SearchFilters, filter_name: str) -> list[FullStudent]:
    if filter_name not in _FILTER_LOOKUP:
        raise ValueError(f"Unknown filter_name: {filter_name}")
    return _FILTER_LOOKUP[filter_name](students, filters)


def filter_students(
    students: list[FullStudent],
    filters: SearchFilters,
    filter_name: Optional[str] = None,
) -> list[FullStudent]:
    if filter_name is None:
        return _apply_filters(students, filters)
    return apply_single_filter(students, filters, filter_name=filter_name)
