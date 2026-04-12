import logging
import re
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


def _matches_free_text(search_query: str, student: FullStudent) -> bool:
    search_query = search_query.strip()
    if not search_query:
        return False

    or_terms = [term.strip() for term in re.split(r"\|", search_query) if term.strip()]
    if not or_terms:
        return False

    return any(_matches_free_text_and_clause(and_clause, student) for and_clause in or_terms)


def _matches_free_text_and_clause(and_clause: str, student: FullStudent) -> bool:
    and_terms = [term.strip() for term in re.split(r"&", and_clause) if term.strip()]
    if not and_terms:
        return False
    return all(_matches_free_text_term(term, student) for term in and_terms)


def _matches_free_text_term(search_query: str, student: FullStudent) -> bool:
    if (
        fuzz.ratio(search_query, student.first_name, processor=utils.default_process)
        >= FREE_TEXT_RATIO_THRESHOLD
    ):
        return True
    if (
        fuzz.partial_ratio(
            search_query, student.photo_comments, processor=utils.default_process
        )
        >= FREE_TEXT_RATIO_THRESHOLD
    ):
        return True
    if (
        fuzz.ratio(search_query, student.religion, processor=utils.default_process)
        >= FREE_TEXT_RATIO_THRESHOLD
    ):
        return True
    if (
        fuzz.partial_ratio(
            search_query, student.allergy_comments, processor=utils.default_process
        )
        >= FREE_TEXT_RATIO_THRESHOLD
    ):
        return True
    if (
        fuzz.partial_ratio(
            search_query,
            student.dietary_restrictions,
            processor=utils.default_process,
        )
        >= FREE_TEXT_RATIO_THRESHOLD
    ):
        return True
    if (
        fuzz.partial_ratio(
            search_query, " ".join(w for w in student.health_comments), processor=utils.default_process
        )
        >= FREE_TEXT_RATIO_THRESHOLD
    ):
        return True
    if (
        fuzz.partial_ratio(
            search_query,
            " ".join(w for w in student.favorite_subjects),
            processor=utils.default_process,
        )
        >= FREE_TEXT_RATIO_THRESHOLD
    ):
        return True
    if (
        fuzz.partial_ratio(
            search_query,
            " ".join(w for w in student.selected_interests),
            processor=utils.default_process,
        )
        >= FREE_TEXT_RATIO_THRESHOLD
    ):
        return True
    if (
        fuzz.partial_ratio(
            search_query,
            " ".join(w for w in student.free_text_interests),
            processor=utils.default_process,
        )
        >= FREE_TEXT_RATIO_THRESHOLD
    ):
        return True
    if (
        fuzz.partial_ratio(
            search_query, student.intro_message, processor=utils.default_process
        )
        >= FREE_TEXT_RATIO_THRESHOLD
    ):
        return True
    if (
        fuzz.partial_ratio(
            search_query,
            student.message_to_host_family,
            processor=utils.default_process,
        )
        >= FREE_TEXT_RATIO_THRESHOLD
    ):
        return True
    if (
        fuzz.partial_ratio(
            search_query,
            student.message_from_natural_family,
            processor=utils.default_process,
        )
        >= FREE_TEXT_RATIO_THRESHOLD
    ):
        return True
    return False


def _filter_free_text(students: list[FullStudent], filters: SearchFilters) -> list[FullStudent]:
    if filters.free_text is None or filters.free_text == "":
        return students

    return [student for student in students if _matches_free_text(filters.free_text, student)]


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
