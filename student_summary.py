from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Iterable

import nltk
from rapidfuzz import fuzz
from sumy.nlp.tokenizers import Tokenizer
from sumy.parsers.plaintext import PlaintextParser
from sumy.summarizers.lex_rank import LexRankSummarizer
from sumy.summarizers.lsa import LsaSummarizer

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from models.student import FullStudent
from repositories.students import get_full_student_by_id

SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
MAX_SENTENCE_CHARS = 220


def _clean_text(value: str | None) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _split_sentences(value: str) -> list[str]:
    text = _clean_text(value)
    if text == "":
        return []
    sentences = [segment.strip() for segment in SENTENCE_SPLIT_RE.split(text) if segment.strip()]
    return sentences if sentences else [text]


def _join_human(items: Iterable[str]) -> str:
    cleaned = [item.strip() for item in items if item and item.strip()]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f"{cleaned[0]} and {cleaned[1]}"
    return f"{', '.join(cleaned[:-1])}, and {cleaned[-1]}"


def _to_float(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _student_narrative_blocks(student: FullStudent) -> list[str]:
    return [student.intro_message, student.message_to_host_family]


def _parent_narrative_blocks(student: FullStudent) -> list[str]:
    return [student.message_from_natural_family]


def _narrative_blocks(student: FullStudent) -> list[str]:
    return [
        *(_student_narrative_blocks(student)),
        *(_parent_narrative_blocks(student)),
        student.photo_comments,
        student.allergy_comments,
        student.dietary_restrictions,
    ]


def _normalize_block(value: str) -> str:
    text = _clean_text(value)
    if text == "":
        return ""
    text = re.sub(r"\|+", ". ", text)
    text = re.sub(r"[_~`]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _is_informative_sentence(sentence: str) -> bool:
    lower = sentence.lower()
    if (
        "this is a photo" in lower
        or "photo with" in lower
        or lower.startswith("this is me")
        or "in front of" in lower
    ):
        return False
    if len(sentence) < 24:
        return False
    alpha_chars = sum(1 for ch in sentence if ch.isalpha())
    if alpha_chars < 15:
        return False
    if alpha_chars / max(1, len(sentence)) < 0.5:
        return False
    return len(sentence.split()) >= 6


def _candidate_sentences_from_blocks(blocks: list[str]) -> list[str]:
    candidates: list[str] = []
    for block in blocks:
        candidates.extend(_split_sentences(_normalize_block(block)))
    return [s for s in candidates if _is_informative_sentence(s)]


def _candidate_sentences(student: FullStudent) -> list[str]:
    return _candidate_sentences_from_blocks(_narrative_blocks(student))


def _student_candidate_sentences(student: FullStudent) -> list[str]:
    return _candidate_sentences_from_blocks(_student_narrative_blocks(student))


def _parent_candidate_sentences(student: FullStudent) -> list[str]:
    return _candidate_sentences_from_blocks(_parent_narrative_blocks(student))


def _clip_sentence(value: str, max_chars: int = MAX_SENTENCE_CHARS) -> str:
    sentence = _clean_text(value).rstrip(".!?")
    if len(sentence) <= max_chars:
        return sentence
    clipped = sentence[: max_chars - 1].rsplit(" ", 1)[0]
    return clipped.strip()


def _normalize_quote(sentence: str) -> str:
    cleaned = _clip_sentence(sentence).strip().strip("'\"")
    if cleaned == "":
        return ""
    if cleaned[-1] not in ".!?":
        cleaned += "."
    return cleaned


def _subject_pronoun(student: FullStudent) -> str:
    return "She" if "female" in _clean_text(student.gender_desc).lower() else "He"


def _possessive_pronoun(student: FullStudent) -> str:
    return "Her" if "female" in _clean_text(student.gender_desc).lower() else "His"


def _facts_sentence(student: FullStudent) -> str:
    age_text = f"{student.adjusted_age}-year-old " if student.adjusted_age else ""
    subject = _subject_pronoun(student)
    placement_pref = ""
    if student.single_placement and student.double_placement:
        placement_pref = f" {subject} is open to either a single or double placement."
    elif student.single_placement:
        placement_pref = f" {subject} prefers a single placement."
    elif student.double_placement:
        placement_pref = f" {subject} prefers a double placement."

    return (
        f"{student.first_name} is a {age_text}student from {student.country}, "
        f"currently in grade {student.current_grade} and applying to grade {student.applying_to_grade} "
        f"through the {student.program_type} program.{placement_pref}"
    )


def _interest_sentence(student: FullStudent) -> str:
    unique_interests = list(
        dict.fromkeys(_clean_text(item) for item in student.selected_interests if _clean_text(item))
    )
    interests = unique_interests[:4]
    favorite_subjects = _clean_text(student.favorite_subjects)
    gpa = _to_float(student.gpa)
    subject = _subject_pronoun(student)
    possessive = _possessive_pronoun(student).lower()

    if interests and favorite_subjects:
        return (
            f"{subject} highlights interests in {_join_human(interests)} and describes "
            f"{possessive} favorite subjects as {favorite_subjects}."
        )
    if interests:
        return f"{subject} highlights interests in {_join_human(interests)}."
    if favorite_subjects:
        return f"{subject} describes {possessive} favorite subjects as {favorite_subjects}."
    if gpa is not None:
        return f"{possessive.capitalize()} profile lists a GPA of {gpa:.2f}."
    return f"{possessive.capitalize()} placement status is currently {student.placement_status}."


def _context_query(student: FullStudent) -> str:
    placement_pref = ""
    if student.single_placement and student.double_placement:
        placement_pref = "single or double placement"
    elif student.single_placement:
        placement_pref = "single placement"
    elif student.double_placement:
        placement_pref = "double placement"

    query_parts = [
        student.first_name,
        student.country,
        student.program_type,
        student.placement_status,
        placement_pref,
        _clean_text(student.favorite_subjects),
        *student.selected_interests[:6],
    ]
    return " ".join(part for part in query_parts if _clean_text(part))


def _highest_signal_sentence(student: FullStudent) -> str:
    candidates = _candidate_sentences(student)
    if not candidates:
        return ""

    query_terms = [
        student.first_name,
        *student.selected_interests[:6],
        _clean_text(student.favorite_subjects),
        _clean_text(student.program_type),
    ]
    query = " ".join(term for term in query_terms if term)
    if query == "":
        return max(candidates, key=len)

    scored = [
        (
            fuzz.token_set_ratio(sentence, query) + min(len(sentence), 140) / 28,
            sentence,
        )
        for sentence in candidates
    ]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return scored[0][1]


def _best_sentence_from_pool(pool: list[str], preferred: list[str], query: str) -> tuple[str, float]:
    if not pool:
        return "", 0.0

    best_sentence = pool[0]
    best_score = -1e9
    for sentence in pool:
        pref_score = max(
            (float(fuzz.token_set_ratio(sentence, ref)) for ref in preferred if ref),
            default=0.0,
        )
        query_score = float(fuzz.token_set_ratio(sentence, query)) if query else 0.0
        score = (pref_score * 0.65) + (query_score * 0.35) + (min(len(sentence), 170) / 60)
        if score > best_score:
            best_sentence = sentence
            best_score = score
    return best_sentence, best_score


def _top_unique_quotes(pool: list[str], query: str, count: int = 3) -> list[str]:
    scored: list[tuple[float, str]] = []
    for sentence in pool:
        query_score = float(fuzz.token_set_ratio(sentence, query)) if query else 0.0
        score = query_score + (min(len(sentence), 170) / 55)
        scored.append((score, sentence))
    ranked = sorted(scored, key=lambda pair: pair[0], reverse=True)

    unique_quotes: list[str] = []
    for _, sentence in ranked:
        quote = _normalize_quote(sentence)
        if quote == "":
            continue
        if any(fuzz.token_set_ratio(quote, existing) >= 86 for existing in unique_quotes):
            continue
        unique_quotes.append(quote)
        if len(unique_quotes) >= count:
            break
    return unique_quotes


def _generate_student_parent_quotes(
    student: FullStudent, quote_count: int = 3
) -> tuple[list[str], list[str]]:
    query = _context_query(student)
    student_quotes = _top_unique_quotes(_student_candidate_sentences(student), query, quote_count)
    parent_quotes = _top_unique_quotes(_parent_candidate_sentences(student), query, quote_count)
    return student_quotes[:quote_count], parent_quotes[:quote_count]


def _select_quotes(
    student: FullStudent, preferred: list[str], parent_variant: int = 0
) -> tuple[str, str]:
    student_quotes, parent_quotes = _generate_student_parent_quotes(student, quote_count=3)
    student_quote = student_quotes[0] if student_quotes else ""
    parent_quote = parent_quotes[0] if parent_quotes else ""
    query = _context_query(student)

    if preferred:
        preferred_quote = _normalize_quote(preferred[0])
        if preferred_quote:
            student_quote, _ = _best_sentence_from_pool(
                [*student_quotes, preferred_quote], preferred, query
            )
            student_quote = _normalize_quote(student_quote)

    if parent_quotes:
        parent_ranked = sorted(
            parent_quotes,
            key=lambda sentence: (
                max(
                    (float(fuzz.token_set_ratio(sentence, ref)) for ref in preferred if ref),
                    default=0.0,
                ),
                float(fuzz.token_set_ratio(sentence, query)) if query else 0.0,
                len(sentence),
            ),
            reverse=True,
        )
        parent_quote = _normalize_quote(parent_ranked[parent_variant % len(parent_ranked)])

    return student_quote, parent_quote


def _render_summary_with_quotes(
    student: FullStudent, student_quote: str, parent_quote: str = ""
) -> str:
    subject = _subject_pronoun(student)
    possessive = _possessive_pronoun(student)
    final_student_quote = student_quote or f"{subject} is eager to learn from a host-family experience."
    parts = [_facts_sentence(student), _interest_sentence(student), f"{subject} says: '{final_student_quote}'"]
    if parent_quote:
        parts.append(f"{possessive} parents say: '{parent_quote}'")
    return " ".join(parts)


def _ensure_nltk_data() -> None:
    for resource in ("punkt", "punkt_tab"):
        try:
            nltk.data.find(f"tokenizers/{resource}")
        except LookupError:
            nltk.download(resource, quiet=True)


def _build_summary_with_sumy(
    student: FullStudent,
    summarizer,
    sentence_count: int = 2,
    parent_variant: int = 0,
) -> str:
    candidates = _candidate_sentences(student)
    if not candidates:
        student_quote, parent_quote = _select_quotes(student, [], parent_variant=parent_variant)
        if student_quote == "":
            student_quote = _normalize_quote(_highest_signal_sentence(student))
        return _render_summary_with_quotes(student, student_quote, parent_quote)

    _ensure_nltk_data()
    parser = PlaintextParser.from_string("\n".join(candidates), Tokenizer("english"))
    summary_items = [str(sentence) for sentence in summarizer(parser.document, sentence_count)]
    if not summary_items:
        summary_items = [_highest_signal_sentence(student)]

    cleaned = [_normalize_quote(s) for s in summary_items if _normalize_quote(s)]
    student_quote, parent_quote = _select_quotes(student, cleaned, parent_variant=parent_variant)
    if student_quote == "" and cleaned:
        student_quote = cleaned[0]
    return _render_summary_with_quotes(student, student_quote, parent_quote)


def build_Result1_lexrank(student: FullStudent) -> str:
    return _build_summary_with_sumy(student, LexRankSummarizer(), parent_variant=2)


def build_Result2_lsa(student: FullStudent) -> str:
    return _build_summary_with_sumy(student, LsaSummarizer(), parent_variant=3)


def Result1_summary(app_id: int) -> str:
    student = get_full_student_by_id(app_id)
    if student is None:
        raise ValueError(f"No FullStudent found for app_id={app_id}.")
    return build_Result1_lexrank(student)


def Result2_summary(app_id: int) -> str:
    student = get_full_student_by_id(app_id)
    if student is None:
        raise ValueError(f"No FullStudent found for app_id={app_id}.")
    return build_Result2_lsa(student)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Standalone Result1/Result2 student summary generator."
    )
    parser.add_argument("--appid", type=int, required=True, help="Student application id.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        summary1 = Result1_summary(args.appid)
        summary2 = Result2_summary(args.appid)
    except ValueError as exc:
        print(str(exc))
        return 1

    student = get_full_student_by_id(args.appid)
    if student is None:
        print(f"No FullStudent found for app_id={args.appid}.")
        return 1

    print("Student Summary (Result1 + Result2)")
    print(f"app_id={student.app_id} | first_name={student.first_name} | country={student.country}")
    print()
    print(f"Result1: {summary1}")
    print()
    print(f"Result2: {summary2}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
