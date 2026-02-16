from __future__ import annotations

import json
import sqlite3
from collections import Counter
from dataclasses import dataclass
from statistics import mean
from typing import Any

from core.config import settings


@dataclass
class Candidate:
    score: int
    app_id: int
    first_name: str
    country: str
    program_type: str
    reasons: list[str]
    interest_overlap_count: int = 0
    interest_match_ratio: float = 0.0


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.database_path)
    conn.row_factory = sqlite3.Row
    return conn


def parse_json_list(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v not in (None, "")]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(v) for v in parsed if v not in (None, "")]
        except json.JSONDecodeError:
            return []
    return []


def to_bool(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)


def get_target_user(conn: sqlite3.Connection, username: str | None) -> sqlite3.Row | None:
    cursor = conn.cursor()
    if username:
        cursor.execute(
            "SELECT username, first_name, favorites FROM users WHERE LOWER(username)=LOWER(?) LIMIT 1",
            (username,),
        )
        user = cursor.fetchone()
        if user is not None:
            return user

    cursor.execute(
        """
        SELECT username, first_name, favorites
        FROM users
        WHERE LOWER(first_name)=LOWER(?)
        ORDER BY username ASC
        LIMIT 1
        """,
        ("Harrison",),
    )
    user = cursor.fetchone()
    if user is not None:
        return user

    cursor.execute(
        "SELECT username, first_name, favorites FROM users WHERE LOWER(username)=LOWER(?) LIMIT 1",
        ("admin",),
    )
    return cursor.fetchone()


def get_students_by_app_ids(conn: sqlite3.Connection, app_ids: list[int]) -> list[sqlite3.Row]:
    if not app_ids:
        return []
    placeholders = ",".join("?" for _ in app_ids)
    cursor = conn.cursor()
    cursor.execute(
        f"SELECT * FROM student_full_view WHERE app_id IN ({placeholders})",
        tuple(app_ids),
    )
    return cursor.fetchall()


def get_all_students(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM student_full_view")
    return cursor.fetchall()


def filter_students_by_compare_scope(
    students: list[sqlite3.Row], compare: str
) -> list[sqlite3.Row]:
    normalized = compare.strip().lower()
    if normalized in ("", "all"):
        return students
    return [
        row
        for row in students
        if normalized in str(row["placement_status"] or "").strip().lower()
    ]


def derive_baseline(favorites: list[sqlite3.Row]) -> tuple[dict[str, Any], dict[str, Any]]:
    countries = Counter()
    genders = Counter()
    programs = Counter()
    interests = Counter()

    gpas: list[float] = []
    ages: list[int] = []
    single_true = 0
    double_true = 0
    pets_true = 0
    has_video = 0

    for row in favorites:
        if row["country"]:
            countries[str(row["country"]).strip()] += 1
        if row["gender_desc"]:
            genders[str(row["gender_desc"]).strip()] += 1
        if row["program_type"]:
            programs[str(row["program_type"]).strip()] += 1

        for item in parse_json_list(row["selected_interests"]):
            interests[item] += 1

        try:
            if row["gpa"] not in (None, ""):
                gpas.append(float(row["gpa"]))
        except (TypeError, ValueError):
            pass

        try:
            if row["adjusted_age"] is not None:
                ages.append(int(row["adjusted_age"]))
        except (TypeError, ValueError):
            pass

        if to_bool(row["single_placement"]):
            single_true += 1
        if to_bool(row["double_placement"]):
            double_true += 1
        if to_bool(row["live_with_pets"]):
            pets_true += 1
        if str(row["media_link"] or "").strip() != "":
            has_video += 1

    baseline_size = max(1, len(favorites))

    min_interest_count = max(1, baseline_size // 3)
    top_interests = [
        name for name, count in interests.most_common() if count >= min_interest_count
    ][:20]
    interest_weights = {name: count for name, count in interests.items()}

    baseline = {
        "country": countries.most_common(1)[0][0] if countries else None,
        "gender": genders.most_common(1)[0][0] if genders else None,
        "program_type": programs.most_common(1)[0][0] if programs else None,
        "gpa_floor": round(mean(gpas), 2) if gpas else None,
        "age_floor": round(mean(ages)) if ages else None,
        "pets_in_home": "yes" if pets_true >= max(1, baseline_size // 2) else "all",
        "has_video": has_video >= max(1, baseline_size // 2),
        "top_interests": top_interests,
        "interest_weights": interest_weights,
    }

    diagnostics = {
        "country_counts": countries,
        "gender_counts": genders,
        "program_counts": programs,
        "interest_counts": interests,
    }
    return baseline, diagnostics


def build_search_filter_payload(baseline: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "statusOptions": ("Unassigned",),
    }

    if baseline["country"]:
        payload["country_of_origin"] = baseline["country"]

    gender = str(baseline["gender"] or "").lower()
    if gender == "male":
        payload["gender_male"] = True
        payload["gender_female"] = False
    elif gender == "female":
        payload["gender_female"] = True
        payload["gender_male"] = False

    if baseline["gpa_floor"] is not None:
        payload["gpa"] = f"{baseline['gpa_floor']:.2f}"
    if baseline["age_floor"] is not None:
        payload["adjusted_age"] = str(baseline["age_floor"])
    if baseline["pets_in_home"] != "all":
        payload["pets_in_home"] = baseline["pets_in_home"]
    if baseline["has_video"]:
        payload["hasVideo"] = True

    if baseline["top_interests"]:
        payload["interests"] = baseline["top_interests"][0]

    return payload


def score_candidates(
    all_students: list[sqlite3.Row],
    favorites: list[sqlite3.Row],
    baseline: dict[str, Any],
) -> list[Candidate]:
    favorite_ids = {int(row["app_id"]) for row in favorites}
    top_interests = set(baseline["top_interests"])
    interest_weights: dict[str, int] = baseline.get("interest_weights", {})
    interest_target_count = max(1, len(top_interests))

    ranked: list[Candidate] = []
    for row in all_students:
        app_id = int(row["app_id"])
        if app_id in favorite_ids:
            continue

        score = 0
        reasons: list[str] = []

        if baseline["country"] and str(row["country"] or "").lower() == str(
            baseline["country"]
        ).lower():
            score += 2
            reasons.append("country match")

        if baseline["gender"] and str(row["gender_desc"] or "").lower() == str(
            baseline["gender"]
        ).lower():
            score += 1
            reasons.append("gender match")

        if baseline["program_type"] and str(baseline["program_type"]).lower() in str(
            row["program_type"] or ""
        ).lower():
            score += 2
            reasons.append("program match")

        try:
            gpa = float(row["gpa"]) if row["gpa"] not in (None, "") else None
            if (
                gpa is not None
                and baseline["gpa_floor"] is not None
                and gpa >= baseline["gpa_floor"]
            ):
                score += 1
                reasons.append("gpa at/above baseline")
        except (TypeError, ValueError):
            pass

        try:
            age = int(row["adjusted_age"]) if row["adjusted_age"] is not None else None
            if (
                age is not None
                and baseline["age_floor"] is not None
                and age >= baseline["age_floor"]
            ):
                score += 1
                reasons.append("age at/above baseline")
        except (TypeError, ValueError):
            pass
        if baseline["pets_in_home"] == "yes" and to_bool(row["live_with_pets"]):
            score += 1
            reasons.append("pets in home")
        if baseline["has_video"] and str(row["media_link"] or "").strip() != "":
            score += 1
            reasons.append("has video")

        student_interests = set(parse_json_list(row["selected_interests"]))
        overlap = sorted(student_interests.intersection(top_interests))
        overlap_count = len(overlap)
        overlap_ratio = overlap_count / interest_target_count
        if overlap:
            weighted_overlap = sum(interest_weights.get(interest, 1) for interest in overlap)
            score += weighted_overlap * 8
            score += int(round(overlap_ratio * 25))
            reasons.append(
                f"interest overlap {overlap_count}/{interest_target_count}: {', '.join(overlap)}"
            )

        if score == 0:
            continue

        ranked.append(
            Candidate(
                score=score,
                app_id=app_id,
                first_name=str(row["first_name"] or ""),
                country=str(row["country"] or ""),
                program_type=str(row["program_type"] or ""),
                reasons=reasons,
                interest_overlap_count=overlap_count,
                interest_match_ratio=overlap_ratio,
            )
        )

    ranked.sort(
        key=lambda item: (
            -item.interest_overlap_count,
            -item.interest_match_ratio,
            -item.score,
            item.app_id,
        )
    )
    return ranked


def print_counter(counter: Counter, title: str, top_n: int = 5) -> None:
    print(f"\n{title}")
    if not counter:
        print("  - none")
        return
    for key, count in counter.most_common(top_n):
        print(f"  - {key}: {count}")


def run_simple_recs() -> int:
    top_n = 3
    compare = "allocated"
    username = None

    conn = get_connection()
    try:
        user = get_target_user(conn, username)
        if user is None:
            print("No matching user found.")
            return 1

        print("Recommendation POC")
        favorites_raw = parse_json_list(user["favorites"])
        favorite_ids = [int(item) for item in favorites_raw if str(item).isdigit()]
        favorite_students = get_students_by_app_ids(conn, favorite_ids)
        unresolved = sorted(set(favorite_ids) - {int(row["app_id"]) for row in favorite_students})

        print(f"User: {user['username']} ({user['first_name']})")
        print("Baseline source: favorites")
        print(f"Favorite app_ids in user profile: {len(favorite_ids)}")

        all_students = get_all_students(conn)
        scoped_students = filter_students_by_compare_scope(all_students, compare)

        print(f"Baseline app_ids resolved in student_full_view: {len(favorite_students)}")
        print(f"Compare scope: {compare} | corpus size in scope: {len(scoped_students)}")
        if unresolved:
            print(f"Unresolved baseline app_ids (not currently in full view): {unresolved}")

        if not favorite_students:
            print("No favorite students available to derive recommendations.")
            return 1

        baseline, diagnostics = derive_baseline(favorite_students)
        payload = build_search_filter_payload(baseline)

        print("\nDerived baseline")
        for key in [
            "country",
            "gender",
            "program_type",
            "gpa_floor",
            "age_floor",
            "pets_in_home",
            "has_video",
            "top_interests",
        ]:
            print(f"  - {key}: {baseline[key]}")

        print_counter(diagnostics["country_counts"], "Favorite countries")
        print_counter(diagnostics["gender_counts"], "Favorite genders")
        print_counter(diagnostics["program_counts"], "Favorite program types")
        print_counter(diagnostics["interest_counts"], "Top favorite interests", top_n=10)

        print("\nSearchFilters-style payload candidate")
        print(json.dumps(payload, indent=2))

        ranked = score_candidates(scoped_students, favorite_students, baseline)

        print(f"\nTop {top_n} recommendation candidates")
        for idx, candidate in enumerate(ranked[:top_n], start=1):
            print(
                f"{idx}. app_id={candidate.app_id} | score={candidate.score} | "
                f"name={candidate.first_name} | country={candidate.country} | "
                f"program={candidate.program_type} | "
                f"interest_overlap={candidate.interest_overlap_count}"
            )
            print(f"   reasons: {', '.join(candidate.reasons)}")

        if not ranked:
            print("No recommendation candidates scored above zero with current heuristic.")

        return 0
    finally:
        conn.close()


def main() -> int:
    return run_simple_recs()


if __name__ == "__main__":
    raise SystemExit(main())
