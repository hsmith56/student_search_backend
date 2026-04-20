from __future__ import annotations

import statistics
import time
from dataclasses import dataclass

from repositories.admin import initialize_db
from repositories.base import get_connection
from repositories.students import (
    clear_student_full_view_cache,
    get_all_full_students,
    get_favorites,
)
from repositories.users import (
    get_user_with_states_by_id,
    list_all_users,
    list_all_users_with_states,
    list_signup_users_for_manager,
    list_users_by_account_type,
    read_user,
)


@dataclass(frozen=True)
class BenchContext:
    user_id: str | None
    username: str | None
    manager_id: str | None
    favorite_ids: list[int]


def _build_context() -> BenchContext:
    with get_connection(row_factory=True) as connection:
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT id, username, manager_id
            FROM users
            ORDER BY rowid DESC
            LIMIT 1
            """
        )
        row = cursor.fetchone()

        cursor.execute(
            """
            SELECT app_id
            FROM student_full_view
            ORDER BY app_id
            LIMIT 40
            """
        )
        favorite_ids = [int(item[0]) for item in cursor.fetchall()]

    if row is None:
        return BenchContext(
            user_id=None,
            username=None,
            manager_id=None,
            favorite_ids=favorite_ids,
        )

    return BenchContext(
        user_id=str(row["id"]),
        username=str(row["username"]),
        manager_id=str(row["manager_id"]) if row["manager_id"] else None,
        favorite_ids=favorite_ids,
    )


def _run_schema_case() -> None:
    initialize_db()


def _run_user_queries_case(context: BenchContext) -> None:
    for _ in range(120):
        list_all_users_with_states()
        list_all_users()
        list_users_by_account_type(account_type="lc")

        if context.user_id is not None:
            get_user_with_states_by_id(user_id=context.user_id)

        if context.username is not None:
            read_user(username=context.username)

        list_signup_users_for_manager(
            requester_id=context.manager_id or "",
            requester_role="rpm",
        )
        list_signup_users_for_manager(
            requester_id=context.user_id or "",
            requester_role="admin",
        )


def _run_student_queries_case() -> None:
    for _ in range(24):
        clear_student_full_view_cache()
        get_all_full_students()


def _run_favorites_case(context: BenchContext) -> None:
    for _ in range(180):
        get_favorites(context.favorite_ids)


def run_once(context: BenchContext) -> tuple[float, dict[str, float]]:
    case_timings_ms: dict[str, float] = {}

    start = time.perf_counter_ns()
    _run_schema_case()
    case_timings_ms["schema_ms"] = (time.perf_counter_ns() - start) / 1_000_000

    start = time.perf_counter_ns()
    _run_user_queries_case(context)
    case_timings_ms["users_ms"] = (time.perf_counter_ns() - start) / 1_000_000

    start = time.perf_counter_ns()
    _run_student_queries_case()
    case_timings_ms["students_ms"] = (time.perf_counter_ns() - start) / 1_000_000

    start = time.perf_counter_ns()
    _run_favorites_case(context)
    case_timings_ms["favorites_ms"] = (time.perf_counter_ns() - start) / 1_000_000

    total_ms = sum(case_timings_ms.values())
    return total_ms, case_timings_ms


def main() -> None:
    context = _build_context()

    warmup_runs = 1
    sample_runs = 7

    for _ in range(warmup_runs):
        run_once(context)

    samples = [run_once(context) for _ in range(sample_runs)]
    total_samples = [sample[0] for sample in samples]

    median_total_ms = statistics.median(total_samples)
    p95_total_ms = statistics.quantiles(total_samples, n=20)[18]

    case_names = ("schema_ms", "users_ms", "students_ms", "favorites_ms")
    case_medians = {
        case_name: statistics.median(sample[1][case_name] for sample in samples)
        for case_name in case_names
    }

    print(f"METRIC total_ms={median_total_ms:.3f}")
    print(f"METRIC p95_total_ms={p95_total_ms:.3f}")
    for case_name in case_names:
        print(f"METRIC {case_name}={case_medians[case_name]:.3f}")


if __name__ == "__main__":
    main()
