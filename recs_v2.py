from __future__ import annotations

import argparse
import json
import re
import sqlite3
from dataclasses import asdict, dataclass
from typing import Any

from core.config import settings
from rapidfuzz import fuzz


@dataclass(frozen=True)
class StudentProfile:
    app_id: int
    usahsid: str
    first_name: str
    placement_status: str
    country: str
    program_type: str
    gender_desc: str
    applying_to_grade: int | None
    adjusted_age: int | None
    gpa: float | None
    english_score: float | None
    selected_interests: list[str]
    extracurricular_interest: str
    states: set[str]
    urban_request: str
    single_placement: bool | None
    double_placement: bool | None
    live_with_pets: bool | None


@dataclass(frozen=True)
class Recommendation:
    app_id: int
    usahsid: str
    first_name: str
    placement_status: str
    score: float
    interest_overlap: int
    state_overlap: int
    reasons: list[str]


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(settings.database_path)
    connection.row_factory = sqlite3.Row
    return connection


def _normalize(value: Any) -> str:
    return str(value or "").strip().lower()


def _parse_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    text = _normalize(value)
    if text in {"1", "true", "yes", "y"}:
        return True
    if text in {"0", "false", "no", "n"}:
        return False
    return None


def _parse_json_set(value: Any) -> set[str]:
    return set(_parse_json_list(value))


def _parse_json_list(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    values: list[str] = []
    if isinstance(value, list):
        values = [_normalize(item) for item in value if _normalize(item)]
    elif isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = []
        if isinstance(parsed, list):
            values = [_normalize(item) for item in parsed if _normalize(item)]

    seen: set[str] = set()
    ordered: list[str] = []
    for item in values:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def _parse_state_preferences(value: Any) -> set[str]:
    if value in (None, ""):
        return set()

    if isinstance(value, list):
        return {_normalize(item) for item in value if _normalize(item)}

    if isinstance(value, str):
        raw = value.strip()
        if raw == "":
            return set()

        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return {_normalize(item) for item in parsed if _normalize(item)}
            if isinstance(parsed, str) and _normalize(parsed):
                return {_normalize(parsed)}
        except json.JSONDecodeError:
            pass

        if any(sep in raw for sep in [",", ";", "|"]):
            parts = re.split(r"[,;|]", raw)
            return {_normalize(part) for part in parts if _normalize(part)}
        return {_normalize(raw)}

    return set()


def _parse_primary_extracurricular(value: Any) -> str:
    entries = _parse_json_list(value)
    if not entries:
        return ""
    primary = entries[0]
    if primary in {"n/a", "na", "none", "no", ".", "/", "-"}:
        return ""
    return primary


def _clean_interest_text(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9\s/&()+-]", " ", _normalize(value))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _split_interest_phrases(value: str) -> list[str]:
    cleaned = _clean_interest_text(value)
    if cleaned == "":
        return []
    parts = re.split(r"[,;/]|\band\b|\bor\b", cleaned)
    phrases: list[str] = []
    for part in parts:
        phrase = part.strip()
        if phrase == "":
            continue
        # Keep compact activity-like phrases, drop long narrative fragments.
        if len(phrase.split()) > 8:
            continue
        phrases.append(phrase)
    if not phrases and cleaned != "":
        phrases = [cleaned]
    seen: set[str] = set()
    ordered: list[str] = []
    for phrase in phrases:
        if phrase not in seen:
            seen.add(phrase)
            ordered.append(phrase)
    return ordered


def _best_fuzzy_match(source: str, targets: list[str]) -> tuple[float, str]:
    if source == "" or not targets:
        return 0.0, ""
    best_score = 0.0
    best_target = ""
    for target in targets:
        if target == "":
            continue
        score = max(
            fuzz.token_set_ratio(source, target) / 100.0,
            fuzz.token_sort_ratio(source, target) / 100.0,
            fuzz.ratio(source, target) / 100.0,
        )
        if score > best_score:
            best_score = score
            best_target = target
    return best_score, best_target


def _shorten(text: str, max_len: int = 48) -> str:
    if len(text) <= max_len:
        return text
    return f"{text[: max_len - 3]}..."


def _candidate_interest_terms(student: StudentProfile) -> list[str]:
    terms: list[str] = []
    for item in student.selected_interests:
        cleaned = _clean_interest_text(item)
        if cleaned != "":
            terms.append(cleaned)
    terms.extend(_split_interest_phrases(student.extracurricular_interest))
    seen: set[str] = set()
    ordered: list[str] = []
    for term in terms:
        if term not in seen:
            seen.add(term)
            ordered.append(term)
    return ordered


def _fuzzy_extracurricular_overlap(
    baseline: StudentProfile, candidate: StudentProfile, threshold: float = 0.78
) -> tuple[int, float, list[str]]:
    baseline_terms = [
        _clean_interest_text(item)
        for item in baseline.selected_interests
        if _clean_interest_text(item) != ""
    ]
    candidate_terms = _split_interest_phrases(candidate.extracurricular_interest)
    if not baseline_terms or not candidate_terms:
        return 0, 0.0, []

    matched_count = 0
    ratio_sum = 0.0
    examples: list[str] = []
    for baseline_term in baseline_terms:
        ratio, matched_term = _best_fuzzy_match(baseline_term, candidate_terms)
        if ratio >= threshold:
            matched_count += 1
            ratio_sum += ratio
            if len(examples) < 3:
                examples.append(
                    f"{_shorten(baseline_term)}~{_shorten(matched_term)} ({ratio:.2f})"
                )

    if matched_count == 0:
        return 0, 0.0, []

    avg_ratio = ratio_sum / matched_count
    coverage = matched_count / max(1, len(baseline_terms))
    overlap_strength = min(1.0, avg_ratio * coverage * 1.25)
    return matched_count, overlap_strength, examples


def _fuzzy_baseline_primary_overlap(
    baseline: StudentProfile, candidate: StudentProfile, threshold: float = 0.86
) -> tuple[int, float, list[str]]:
    baseline_text = _clean_interest_text(baseline.extracurricular_interest)
    candidate_terms = _candidate_interest_terms(candidate)
    if baseline_text == "" or not candidate_terms:
        return 0, 0.0, []

    generic_singletons = {
        "sport",
        "sports",
        "music",
        "team",
        "club",
        "school",
        "student",
        "students",
    }
    matched: list[tuple[str, float]] = []
    for candidate_term in candidate_terms:
        term = _clean_interest_text(candidate_term)
        if term == "":
            continue
        tokens = term.split()
        if len(tokens) == 1 and tokens[0] in generic_singletons:
            continue
        ratio = max(
            fuzz.token_set_ratio(term, baseline_text) / 100.0,
            fuzz.partial_ratio(term, baseline_text) / 100.0,
            fuzz.ratio(term, baseline_text) / 100.0,
        )
        if ratio >= threshold:
            matched.append((term, ratio))

    if not matched:
        return 0, 0.0, []

    matched.sort(key=lambda item: item[1], reverse=True)
    deduped: list[tuple[str, float]] = []
    seen_terms: set[str] = set()
    for term, ratio in matched:
        if term in seen_terms:
            continue
        seen_terms.add(term)
        deduped.append((term, ratio))
        if len(deduped) >= 5:
            break

    matched_count = len(deduped)
    ratio_sum = sum(ratio for _, ratio in deduped)
    avg_ratio = ratio_sum / matched_count
    coverage = min(1.0, matched_count / 3.0)
    overlap_strength = min(1.0, avg_ratio * coverage * 1.15)
    examples = [
        f"{_shorten(term)}~baseline_extracurricular[0] ({ratio:.2f})"
        for term, ratio in deduped[:3]
    ]

    return matched_count, overlap_strength, examples


def _row_to_student(row: sqlite3.Row) -> StudentProfile:
    return StudentProfile(
        app_id=int(row["app_id"]),
        usahsid=str(row["usahsid"] or ""),
        first_name=str(row["first_name"] or ""),
        placement_status=str(row["placement_status"] or ""),
        country=str(row["country"] or ""),
        program_type=str(row["program_type"] or ""),
        gender_desc=str(row["gender_desc"] or ""),
        applying_to_grade=_parse_int(row["applying_to_grade"]),
        adjusted_age=_parse_int(row["adjusted_age"]),
        gpa=_parse_float(row["gpa"]),
        english_score=_parse_float(row["english_score"]),
        selected_interests=_parse_json_list(row["selected_interests"]),
        extracurricular_interest=_parse_primary_extracurricular(
            row["free_text_interests"]
        ),
        states=_parse_json_set(row["states"]),
        urban_request=str(row["urban_request"] or ""),
        single_placement=_parse_bool(row["single_placement"]),
        double_placement=_parse_bool(row["double_placement"]),
        live_with_pets=_parse_bool(row["live_with_pets"]),
    )


def _load_student_by_usahsid(
    connection: sqlite3.Connection, usahsid: str
) -> StudentProfile | None:
    cursor = connection.cursor()
    cursor.execute(
        """
        SELECT
            app_id, usahsid, first_name, placement_status, country, program_type,
            gender_desc, applying_to_grade, adjusted_age, gpa, english_score,
            selected_interests, free_text_interests, states, urban_request, single_placement,
            double_placement, live_with_pets
        FROM student_full_view
        WHERE LOWER(COALESCE(usahsid, '')) = LOWER(?)
        LIMIT 1
        """,
        (usahsid,),
    )
    row = cursor.fetchone()
    return _row_to_student(row) if row else None


def _load_all_other_students(
    connection: sqlite3.Connection, baseline_app_id: int
) -> list[StudentProfile]:
    cursor = connection.cursor()
    cursor.execute(
        """
        SELECT
            app_id, usahsid, first_name, placement_status, country, program_type,
            gender_desc, applying_to_grade, adjusted_age, gpa, english_score,
            selected_interests, free_text_interests, states, urban_request, single_placement,
            double_placement, live_with_pets
        FROM student_full_view
        WHERE app_id != ?
        """,
        (baseline_app_id,),
    )
    return [_row_to_student(row) for row in cursor.fetchall()]


def _load_user_preferred_states(
    connection: sqlite3.Connection, username: str
) -> set[str] | None:
    cursor = connection.cursor()
    cursor.execute(
        """
        SELECT
            placing_states,
            "Placing State" AS legacy_placing_state
        FROM users
        WHERE LOWER(username) = LOWER(?)
        LIMIT 1
        """,
        (username,),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    normalized_states: set[str] = set()
    normalized_states.update(_parse_state_preferences(row["placing_states"]))
    normalized_states.update(_parse_state_preferences(row["legacy_placing_state"]))
    return normalized_states


def _resolve_state_reference(
    connection: sqlite3.Connection,
    baseline_states: set[str],
    username: str | None,
) -> tuple[set[str], str]:
    if not username:
        return baseline_states, "baseline states"

    user_states = _load_user_preferred_states(connection, username)
    if user_states is None:
        raise ValueError(f"No user found for username={username!r}")
    if user_states:
        return user_states, f"user preferred states ({username})"
    return baseline_states, f"baseline states (user {username} has no preferred states)"


def _filter_by_scope(
    students: list[StudentProfile], compare: str
) -> list[StudentProfile]:
    normalized = _normalize(compare)
    if normalized in {"", "all"}:
        return students
    return [
        student
        for student in students
        if normalized in _normalize(student.placement_status)
    ]


def _jaccard_overlap(first: set[str], second: set[str]) -> tuple[int, float]:
    if not first or not second:
        return 0, 0.0
    overlap = len(first.intersection(second))
    union = len(first.union(second))
    if union == 0:
        return 0, 0.0
    return overlap, overlap / union


def _score_candidate(
    baseline: StudentProfile,
    candidate: StudentProfile,
    state_reference: set[str],
    state_reason_label: str,
    priority_interests: list[str] | None = None,
) -> tuple[float, int, int, list[str]]:
    score = 0.0
    reasons: list[str] = []

    baseline_interest_set = set(baseline.selected_interests)
    candidate_interest_set = set(candidate.selected_interests)
    interest_overlap, interest_jaccard = _jaccard_overlap(
        baseline_interest_set, candidate_interest_set
    )
    if interest_overlap > 0:
        score += 100.0 * interest_jaccard
        shared_interests = sorted(
            baseline_interest_set.intersection(candidate_interest_set)
        )
        reasons.append(
            f"shared interests ({interest_overlap}): {', '.join(shared_interests[:6])}"
        )

    fuzzy_overlap_count, fuzzy_overlap_strength, fuzzy_examples = (
        _fuzzy_extracurricular_overlap(baseline, candidate)
    )
    if fuzzy_overlap_count > 0:
        score += 18.0 * fuzzy_overlap_strength
        reasons.append(
            f"fuzzy extracurricular overlap ({fuzzy_overlap_count}): "
            f"{', '.join(fuzzy_examples)}"
        )

    baseline_primary_count, baseline_primary_strength, baseline_primary_examples = (
        _fuzzy_baseline_primary_overlap(baseline, candidate)
    )
    if baseline_primary_count > 0:
        score += 30.0 * baseline_primary_strength
        reasons.append(
            "baseline extracurricular[0] overlap "
            f"({baseline_primary_count}): {', '.join(baseline_primary_examples)}"
        )

    candidate_interest_terms = _candidate_interest_terms(candidate)
    for priority_interest in priority_interests or []:
        normalized_priority_interest = _normalize(priority_interest)
        if normalized_priority_interest == "":
            continue
        priority_source = _clean_interest_text(normalized_priority_interest)
        priority_ratio, priority_match = _best_fuzzy_match(
            priority_source, candidate_interest_terms
        )
        if priority_ratio >= 0.90:
            score += 30.0
            reasons.append(
                f"priority interest fuzzy match: {normalized_priority_interest}~"
                f"{_shorten(priority_match)} ({priority_ratio:.2f})"
            )
        elif priority_ratio >= 0.82:
            score += 24.0
            reasons.append(
                f"priority interest fuzzy match: {normalized_priority_interest}~"
                f"{_shorten(priority_match)} ({priority_ratio:.2f})"
            )
        elif priority_ratio >= 0.75:
            score += 16.0
            reasons.append(
                f"priority interest fuzzy match: {normalized_priority_interest}~"
                f"{_shorten(priority_match)} ({priority_ratio:.2f})"
            )

    state_overlap, state_jaccard = _jaccard_overlap(state_reference, candidate.states)
    if state_overlap > 0:
        score += 40.0 * state_jaccard
        reasons.append(f"{state_reason_label} ({state_overlap})")

    if _normalize(baseline.country) and _normalize(baseline.country) == _normalize(
        candidate.country
    ):
        score += 15.0
        reasons.append("same country")

    if _normalize(baseline.program_type) and _normalize(
        baseline.program_type
    ) == _normalize(candidate.program_type):
        score += 15.0
        reasons.append("same program")

    if _normalize(baseline.gender_desc) and _normalize(baseline.gender_desc) == _normalize(
        candidate.gender_desc
    ):
        score += 7.0
        reasons.append("same gender")

    if (
        baseline.applying_to_grade is not None
        and candidate.applying_to_grade is not None
    ):
        grade_diff = abs(baseline.applying_to_grade - candidate.applying_to_grade)
        if grade_diff == 0:
            score += 11.0
            reasons.append("same applying grade")
        elif grade_diff == 1:
            score += 6.0
            reasons.append("near applying grade")

    if baseline.adjusted_age is not None and candidate.adjusted_age is not None:
        age_diff = abs(baseline.adjusted_age - candidate.adjusted_age)
        if age_diff == 0:
            score += 8.0
            reasons.append("same age")
        elif age_diff == 1:
            score += 5.0
            reasons.append(f"1 year {'older' if candidate.adjusted_age > baseline.adjusted_age else 'younger'}")

    if baseline.gpa is not None and candidate.gpa is not None:
        gpa_diff = abs(baseline.gpa - candidate.gpa)
        if gpa_diff <= 0.20:
            score += 9.0
            reasons.append("very close GPA")
        elif gpa_diff <= 0.50:
            score += 5.0
            reasons.append("close GPA")

    if baseline.english_score is not None and candidate.english_score is not None:
        english_diff = abs(baseline.english_score - candidate.english_score)
        if english_diff <= 5:
            score += 6.0
            reasons.append("very close English score")
        elif english_diff <= 10:
            score += 4.0
            reasons.append("close English score")

    if _normalize(baseline.urban_request) and _normalize(baseline.urban_request) == _normalize(
        candidate.urban_request
    ):
        score += 3.0
        reasons.append("same urban request")

    if (
        baseline.single_placement is not None
        and candidate.single_placement is not None
        and baseline.single_placement == candidate.single_placement
    ):
        score += 2.0
        reasons.append("single placement preference match")

    if (
        baseline.double_placement is not None
        and candidate.double_placement is not None
        and baseline.double_placement == candidate.double_placement
    ):
        score += 2.0
        reasons.append("double placement preference match")

    if (
        baseline.live_with_pets is not None
        and candidate.live_with_pets is not None
        and baseline.live_with_pets == candidate.live_with_pets
    ):
        score += 2.0
        reasons.append("pets preference match")

    return round(score, 4), interest_overlap, state_overlap, reasons


def get_recommendations(
    usahsid: str,
    n: int = 10,
    compare: str = "all",
    username: str | None = None,
    priority_interests: list[str] | None = None,
) -> list[Recommendation]:
    if n <= 0:
        raise ValueError("n must be greater than 0")

    with get_connection() as connection:
        baseline = _load_student_by_usahsid(connection, usahsid)
        if baseline is None:
            raise ValueError(f"No student found for usahsid={usahsid!r}")
        state_reference, state_reference_source = _resolve_state_reference(
            connection, baseline.states, username
        )
        using_user_state_preferences = (
            username is not None
            and state_reference_source.startswith("user preferred states")
        )
        state_reason_label = (
            "user preferred state overlap"
            if using_user_state_preferences
            else "state overlap"
        )

        candidates = _load_all_other_students(connection, baseline.app_id)
        candidates = _filter_by_scope(candidates, compare)

        ranked: list[Recommendation] = []
        for candidate in candidates:
            score, interest_overlap, state_overlap, reasons = _score_candidate(
                baseline,
                candidate,
                state_reference,
                state_reason_label,
                priority_interests=priority_interests,
            )
            if score <= 0:
                continue
            ranked.append(
                Recommendation(
                    app_id=candidate.app_id,
                    usahsid=candidate.usahsid,
                    first_name=candidate.first_name,
                    placement_status=candidate.placement_status,
                    score=score,
                    interest_overlap=interest_overlap,
                    state_overlap=state_overlap,
                    reasons=reasons,
                )
            )

        ranked.sort(
            key=lambda item: (
                -item.score,
                -item.interest_overlap,
                -item.state_overlap,
                item.app_id,
            )
        )
        return ranked[:n]


def _format_recommendations_table(
    baseline: StudentProfile,
    recommendations: list[Recommendation],
    state_reference_source: str,
    state_reference: set[str],
    priority_interests: list[str] | None = None,
) -> str:
    state_display = ", ".join(sorted(state_reference)) if state_reference else "none"
    priority_display = (
        ", ".join(_normalize(item) for item in priority_interests if _normalize(item))
        if priority_interests
        else "none"
    )
    lines = [
        f"Baseline: usahsid={baseline.usahsid} | app_id={baseline.app_id} | "
        f"name={baseline.first_name} | status={baseline.placement_status}",
        f"State reference: {state_reference_source} | values={state_display}",
        "Baseline extracurricular[0]: "
        f"{baseline.extracurricular_interest or 'none'}",
        f"Priority interest: {priority_display}",
        f"Returned recommendations: {len(recommendations)}",
        "",
    ]

    if not recommendations:
        lines.append("No recommendation candidates scored above zero.")
        return "\n".join(lines)

    for index, rec in enumerate(recommendations, start=1):
        lines.append(
            f"{index}. app_id={rec.app_id} | usahsid={rec.usahsid} | "
            f"name={rec.first_name} | status={rec.placement_status} | "
            f"score={rec.score:.2f} | interest_overlap={rec.interest_overlap}"
        )
        lines.append(f"   reasons: {', '.join(rec.reasons)}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Structured-content recommender using a baseline usahsid."
    )
    parser.add_argument("usahsid", type=str, help="Baseline student usahsid.")
    parser.add_argument(
        "-n",
        "--num-recs",
        type=int,
        default=10,
        help="Number of recommendations to return.",
    )
    parser.add_argument(
        "--compare",
        type=str,
        default="allocated",
        help="Status scope filter (all, unassigned, allocated, etc).",
    )
    parser.add_argument(
        "--username",
        type=str,
        default=None,
        help='Optional username. If user has "Placing State" values, those override baseline states.',
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Print recommendations as JSON.",
    )
    args = parser.parse_args()

    if args.num_recs <= 0:
        print("num-recs must be greater than 0.")
        return 2

    with get_connection() as connection:
        baseline = _load_student_by_usahsid(connection, args.usahsid)
        if baseline is None:
            print(f"No student found for usahsid={args.usahsid!r}.")
            return 1
        try:
            state_reference, state_reference_source = _resolve_state_reference(
                connection, baseline.states, args.username
            )
        except ValueError as error:
            print(str(error))
            return 1

    priority_interests: list[str] = []
    prompt_options = baseline.selected_interests[:5]
    if prompt_options:
        print("\nOptional: prioritize baseline interests heavily.")
        print(
            "Select one or more priority interests by number (1-5). "
            "Use comma-separated values, or press Enter to skip."
        )
        for idx, interest in enumerate(prompt_options, start=1):
            print(f"  {idx}. {interest}")
        try:
            selection = input("Priority interest number(s): ").strip()
        except EOFError:
            selection = ""
        if selection != "":
            parts = [item.strip() for item in selection.split(",") if item.strip() != ""]
            selected_indices: list[int] = []
            invalid_input = False
            for part in parts:
                if not part.isdigit():
                    invalid_input = True
                    break
                selected_idx = int(part)
                if selected_idx < 1 or selected_idx > len(prompt_options):
                    invalid_input = True
                    break
                selected_indices.append(selected_idx)
            if invalid_input or not selected_indices:
                print("Invalid input. Continuing without priority interests.")
            else:
                seen: set[int] = set()
                for selected_idx in selected_indices:
                    if selected_idx not in seen:
                        seen.add(selected_idx)
                        priority_interests.append(prompt_options[selected_idx - 1])

    recommendations = get_recommendations(
        usahsid=args.usahsid,
        n=args.num_recs,
        compare=args.compare,
        username=args.username,
        priority_interests=priority_interests,
    )

    if args.json:
        print(json.dumps([asdict(item) for item in recommendations], indent=2))
    else:
        print(
            _format_recommendations_table(
                baseline,
                recommendations,
                state_reference_source,
                state_reference,
                priority_interests=priority_interests,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
