from __future__ import annotations

import statistics
import time
from dataclasses import dataclass

from models.search_filters import SearchFilters
from repositories.base import get_connection
from routers.students import ItemQueryParams, apply_filters, run_student_search


@dataclass(frozen=True)
class WorkloadCase:
    name: str
    filters: SearchFilters
    current_user: dict


def _sample_favorites(limit: int = 30) -> list[int]:
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT app_id FROM student_full_view ORDER BY app_id LIMIT ?", (limit,))
        return [int(row[0]) for row in cursor.fetchall()]


def _build_workload() -> list[WorkloadCase]:
    favorite_ids = _sample_favorites(30)

    return [
        WorkloadCase(
            name="baseline_all",
            filters=SearchFilters(),
            current_user={"favorites": "[]"},
        ),
        WorkloadCase(
            name="structured_filters",
            filters=SearchFilters(
                gender_female=True,
                gender_male=False,
                state=("CA", "TX", "FL"),
                statusOptions=("Allocated", "Unassigned"),
                adjusted_age="16",
                gpa="3.0",
                hasVideo=True,
                country_of_origin=("Brazil", "Japan", "Germany"),
                interests=("music", "sports", "reading"),
            ),
            current_user={"favorites": "[]"},
        ),
        WorkloadCase(
            name="free_text",
            filters=SearchFilters(
                free_text="soccer & allergy | catholic",
                statusOptions=("Unassigned",),
            ),
            current_user={"favorites": "[]"},
        ),
        WorkloadCase(
            name="favorites",
            filters=SearchFilters(
                only_favorites=True,
                statusOptions=("Allocated", "Unassigned"),
            ),
            current_user={"favorites": str(favorite_ids).replace("'", '"')},
        ),
    ]


def run_once(workload: list[WorkloadCase]) -> tuple[float, int]:
    params = ItemQueryParams()
    total_ms = 0.0
    total_results = 0

    for case in workload:
        apply_filters.cache_clear()
        start_ns = time.perf_counter_ns()
        response = run_student_search(
            filters=case.filters,
            page=1,
            page_size=21,
            params=params,
            current_user=case.current_user,
        )
        elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
        total_ms += elapsed_ms
        total_results += int(response["total_results"])

    return total_ms, total_results


def main() -> None:
    workload = _build_workload()

    warmup_runs = 2
    sample_runs = 9

    for _ in range(warmup_runs):
        run_once(workload)

    samples = [run_once(workload) for _ in range(sample_runs)]
    total_ms_samples = [sample[0] for sample in samples]
    total_results_samples = [sample[1] for sample in samples]

    median_total_ms = statistics.median(total_ms_samples)
    p95_total_ms = statistics.quantiles(total_ms_samples, n=20)[18]
    median_results = int(statistics.median(total_results_samples))

    print(f"METRIC total_ms={median_total_ms:.3f}")
    print(f"METRIC p95_total_ms={p95_total_ms:.3f}")
    print(f"METRIC total_results={median_results}")


if __name__ == "__main__":
    main()
