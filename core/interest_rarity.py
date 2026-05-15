from collections import Counter
import math
from typing import Any

from repositories.base import get_connection
from repositories.students import (
    AVAILABLE_TO_PLACE_STATUSES,
    _parse_interest_list,
    _sorted_interest_counts,
    _to_title_case_interest_label,
)


def _rarity_label(percentile: float) -> str:
    if percentile >= 90:
        return "very_rare"
    if percentile >= 75:
        return "rare"
    if percentile >= 50:
        return "somewhat_uncommon"
    if percentile >= 25:
        return "common"
    return "very_common"


def _percentile_by_score(scores: list[float]) -> dict[float, float]:
    score_counts = Counter(scores)
    total_scores = len(scores)
    cumulative_count = 0
    percentiles: dict[float, float] = {}

    for score in sorted(score_counts):
        cumulative_count += score_counts[score]
        percentiles[score] = round((cumulative_count / total_scores) * 100, 2)

    return percentiles


def _percentile_value(sorted_values: list[float], percentile: float) -> float:
    if len(sorted_values) == 0:
        return 0.0
    index = round(percentile * (len(sorted_values) - 1))
    return sorted_values[index]


def _metric_distribution(values: list[float]) -> dict[str, float | int]:
    if len(values) == 0:
        return {
            "count": 0,
            "min": 0.0,
            "mean": 0.0,
            "median": 0.0,
            "p75": 0.0,
            "p90": 0.0,
            "p95": 0.0,
            "max": 0.0,
        }

    sorted_values = sorted(values)
    return {
        "count": len(values),
        "min": round(sorted_values[0], 2),
        "mean": round(sum(sorted_values) / len(sorted_values), 2),
        "median": round(_percentile_value(sorted_values, 0.5), 2),
        "p75": round(_percentile_value(sorted_values, 0.75), 2),
        "p90": round(_percentile_value(sorted_values, 0.9), 2),
        "p95": round(_percentile_value(sorted_values, 0.95), 2),
        "max": round(sorted_values[-1], 2),
    }


def _interest_count_entries(
    counts: Counter[str],
    display_labels: dict[str, str],
    *,
    rarest_first: bool,
    limit: int,
    comparison_group_size: int,
) -> list[dict[str, Any]]:
    sorted_items = sorted(
        counts.items(),
        key=lambda item: (
            item[1], display_labels[item[0]].casefold()
        )
        if rarest_first
        else (-item[1], display_labels[item[0]].casefold()),
    )
    return [
        {
            "interest": display_labels[interest_key],
            "student_count": count,
            "student_percent": round((count / comparison_group_size) * 100, 2),
        }
        for interest_key, count in sorted_items[:limit]
    ]


def _sort_student_rarity_results(
    students: list[dict[str, Any]], sort: str
) -> list[dict[str, Any]]:
    sort_key = sort.strip().casefold()
    descending_sorts = {
        "overall_rarity_score",
        "interest_rarity_score",
        "overlap_rarity_score",
        "nearest_neighbor_uniqueness_score",
        "rarity_percentile",
        "selected_interest_count",
    }
    ascending_sorts = {
        "overlap_student_count",
        "overlap_student_percent",
        "nearest_neighbor_similarity",
    }

    if sort_key in descending_sorts:
        return sorted(
            students,
            key=lambda item: (item[sort_key], item["interest_rarity_score"]),
            reverse=True,
        )
    if sort_key in ascending_sorts:
        return sorted(students, key=lambda item: (item[sort_key], -item["app_id"]))

    return sorted(
        students,
        key=lambda item: (
            item["overall_rarity_score"],
            item["interest_rarity_score"],
            -item["overlap_student_count"],
            item["app_id"],
        ),
        reverse=True,
    )


def get_allocated_student_interest_rarity(
    top_matches_per_student: int = 5,
    limit: int | None = 50,
    include_similar_students: bool = False,
    sort: str = "overall_rarity_score",
) -> dict[str, Any]:
    connection = get_connection(row_factory=True)
    cursor = connection.cursor()
    cursor.execute(
        """
    SELECT
        app_id,
        first_name,
        country,
        selected_interests
    FROM student_full_view
    WHERE LOWER(placement_status) IN (?)
    """,
        tuple(AVAILABLE_TO_PLACE_STATUSES),
    )
    rows = cursor.fetchall()
    connection.close()

    included_students: list[dict[str, Any]] = []
    excluded_without_interests = 0
    display_labels: dict[str, str] = {}

    for row in rows:
        interest_keys: set[str] = set()
        for interest in _parse_interest_list(row["selected_interests"]):
            interest_key = interest.casefold()
            interest_keys.add(interest_key)
            display_labels.setdefault(
                interest_key, _to_title_case_interest_label(interest)
            )

        if len(interest_keys) == 0:
            excluded_without_interests += 1
            continue

        included_students.append(
            {
                "app_id": row["app_id"],
                "first_name": row["first_name"],
                "country": row["country"],
                "interest_keys": interest_keys,
            }
        )

    comparison_group_size = len(included_students)
    if comparison_group_size == 0:
        return {
            "comparison_group": "allocated_students",
            "comparison_group_size": 0,
            "excluded_without_interests": excluded_without_interests,
            "summary": {
                "comparison_group": "allocated_students",
                "comparison_group_size": 0,
                "returned_student_count": 0,
                "excluded_without_interests": excluded_without_interests,
                "interest_count": 0,
            },
            "interest_frequencies": {},
            "students": [],
        }

    interest_counts: Counter[str] = Counter()
    for student in included_students:
        interest_counts.update(student["interest_keys"])

    max_idf = math.log(comparison_group_size) if comparison_group_size > 1 else 0.0
    idf_by_interest = {
        interest_key: math.log(comparison_group_size / count)
        for interest_key, count in interest_counts.items()
    }
    duplicate_interest_sets: Counter[tuple[str, ...]] = Counter(
        tuple(sorted(student["interest_keys"])) for student in included_students
    )

    raw_results: list[dict[str, Any]] = []
    for student in included_students:
        student_interest_keys = student["interest_keys"]
        interest_idfs = [idf_by_interest[key] for key in student_interest_keys]
        average_idf = sum(interest_idfs) / len(interest_idfs)
        interest_rarity_score = (
            (average_idf / max_idf) * 100 if max_idf > 0 else 0.0
        )

        overlap_student_count = 0
        max_shared_interest_count = 0
        exact_interest_set_match_count = 0
        similar_students: list[dict[str, Any]] = []

        for other_student in included_students:
            if other_student["app_id"] == student["app_id"]:
                continue

            shared_interest_keys = (
                student_interest_keys & other_student["interest_keys"]
            )
            shared_interest_count = len(shared_interest_keys)
            if shared_interest_count == 0:
                continue

            overlap_student_count += 1
            max_shared_interest_count = max(
                max_shared_interest_count, shared_interest_count
            )
            if student_interest_keys == other_student["interest_keys"]:
                exact_interest_set_match_count += 1

            similar_students.append(
                {
                    "app_id": other_student["app_id"],
                    "first_name": other_student["first_name"],
                    "country": other_student["country"],
                    "shared_interest_count": shared_interest_count,
                    "student_interest_overlap_ratio": round(
                        shared_interest_count / len(student_interest_keys), 4
                    ),
                    "jaccard_similarity": round(
                        shared_interest_count
                        / len(student_interest_keys | other_student["interest_keys"]),
                        4,
                    ),
                    "shared_interests": sorted(
                        (display_labels[key] for key in shared_interest_keys),
                        key=str.casefold,
                    ),
                }
            )

        similar_students.sort(
            key=lambda item: (
                item["jaccard_similarity"], item["shared_interest_count"]
            ),
            reverse=True,
        )
        nearest_neighbor_similarity = (
            similar_students[0]["jaccard_similarity"] if similar_students else 0.0
        )
        nearest_neighbor_uniqueness_score = (1 - nearest_neighbor_similarity) * 100
        overlap_student_percent = (
            (overlap_student_count / (comparison_group_size - 1)) * 100
            if comparison_group_size > 1
            else 0.0
        )
        overlap_rarity_score = 100 - overlap_student_percent
        overall_rarity_score = (
            0.55 * interest_rarity_score
            + 0.25 * nearest_neighbor_uniqueness_score
            + 0.20 * overlap_rarity_score
        )

        result = {
            "app_id": student["app_id"],
            "first_name": student["first_name"],
            "country": student["country"],
            "overall_rarity_score": round(overall_rarity_score, 2),
            "interest_rarity_score": round(interest_rarity_score, 2),
            "overlap_rarity_score": round(overlap_rarity_score, 2),
            "nearest_neighbor_similarity": round(nearest_neighbor_similarity, 4),
            "nearest_neighbor_uniqueness_score": round(
                nearest_neighbor_uniqueness_score, 2
            ),
            "average_interest_idf": round(average_idf, 4),
            "selected_interest_count": len(student_interest_keys),
            "low_interest_count": len(student_interest_keys) < 3,
            "interests": sorted(
                (display_labels[key] for key in student_interest_keys),
                key=str.casefold,
            ),
            "unique_interests": sorted(
                (
                    display_labels[key]
                    for key in student_interest_keys
                    if interest_counts[key] == 1
                ),
                key=str.casefold,
            ),
            "rarest_interests": sorted(
                (
                    {
                        "interest": display_labels[key],
                        "student_count": interest_counts[key],
                        "student_percent": round(
                            (interest_counts[key] / comparison_group_size) * 100,
                            2,
                        ),
                        "idf": round(idf_by_interest[key], 4),
                    }
                    for key in student_interest_keys
                ),
                key=lambda item: (item["student_count"], item["interest"]),
            ),
            "overlap_student_count": overlap_student_count,
            "overlap_student_percent": round(overlap_student_percent, 2),
            "max_shared_interest_count": max_shared_interest_count,
            "exact_interest_set_match_count": exact_interest_set_match_count,
            "duplicate_interest_set_count": duplicate_interest_sets[
                tuple(sorted(student_interest_keys))
            ]
            - 1,
        }
        if include_similar_students:
            result["most_similar_students"] = similar_students[:top_matches_per_student]

        raw_results.append(result)

    overall_percentiles = _percentile_by_score(
        [student["overall_rarity_score"] for student in raw_results]
    )
    interest_percentiles = _percentile_by_score(
        [student["interest_rarity_score"] for student in raw_results]
    )
    for student in raw_results:
        percentile = overall_percentiles[student["overall_rarity_score"]]
        student["rarity_percentile"] = percentile
        student["overall_rarity_percentile"] = percentile
        student["interest_rarity_percentile"] = interest_percentiles[
            student["interest_rarity_score"]
        ]
        student["rarity_label"] = _rarity_label(percentile)

    sorted_results = _sort_student_rarity_results(raw_results, sort)
    if limit is not None and limit > 0:
        sorted_results = sorted_results[:limit]

    interest_frequencies = _sorted_interest_counts(interest_counts, display_labels)
    duplicate_interest_set_count = sum(
        1 for count in duplicate_interest_sets.values() if count > 1
    )
    students_in_duplicate_interest_sets = sum(
        count for count in duplicate_interest_sets.values() if count > 1
    )

    return {
        "comparison_group": "allocated_students",
        "comparison_group_size": comparison_group_size,
        "excluded_without_interests": excluded_without_interests,
        "summary": {
            "comparison_group": "allocated_students",
            "comparison_group_size": comparison_group_size,
            "returned_student_count": len(sorted_results),
            "excluded_without_interests": excluded_without_interests,
            "interest_count": len(interest_counts),
            "zero_overlap_student_count": sum(
                1 for student in raw_results if student["overlap_student_count"] == 0
            ),
            "students_with_unique_interests_count": sum(
                1 for student in raw_results if len(student["unique_interests"]) > 0
            ),
            "duplicate_interest_set_count": duplicate_interest_set_count,
            "students_in_duplicate_interest_sets": students_in_duplicate_interest_sets,
            "low_interest_count_students": sum(
                1 for student in raw_results if student["low_interest_count"]
            ),
            "most_common_interests": _interest_count_entries(
                interest_counts,
                display_labels,
                rarest_first=False,
                limit=10,
                comparison_group_size=comparison_group_size,
            ),
            "rarest_interests": _interest_count_entries(
                interest_counts,
                display_labels,
                rarest_first=True,
                limit=10,
                comparison_group_size=comparison_group_size,
            ),
            "distributions": {
                "overall_rarity_score": _metric_distribution(
                    [student["overall_rarity_score"] for student in raw_results]
                ),
                "interest_rarity_score": _metric_distribution(
                    [student["interest_rarity_score"] for student in raw_results]
                ),
                "overlap_student_count": _metric_distribution(
                    [student["overlap_student_count"] for student in raw_results]
                ),
                "nearest_neighbor_similarity": _metric_distribution(
                    [student["nearest_neighbor_similarity"] for student in raw_results]
                ),
            },
        },
        "scoring": {
            "interest_matching": "exact_case_insensitive_selected_interests",
            "primary_score": "overall_rarity_score",
            "overall_formula": (
                "0.55 * interest_rarity_score + "
                "0.25 * nearest_neighbor_uniqueness_score + "
                "0.20 * overlap_rarity_score"
            ),
            "interest_rarity_formula": (
                "average(log(N / interest_student_count)) / log(N) * 100"
            ),
            "overlap_rarity_formula": "100 - overlap_student_percent",
            "nearest_neighbor_similarity": (
                "highest Jaccard similarity to any other allocated student"
            ),
            "percentile": (
                "percentage of included allocated students with "
                "overall_rarity_score less than or equal to this student"
            ),
            "labels": {
                "very_rare": "90th percentile and above",
                "rare": "75th to 89.99th percentile",
                "somewhat_uncommon": "50th to 74.99th percentile",
                "common": "25th to 49.99th percentile",
                "very_common": "below 25th percentile",
            },
        },
        "sort": sort,
        "limit": limit,
        "include_similar_students": include_similar_students,
        "interest_frequencies": interest_frequencies,
        "students": sorted_results,
    }
