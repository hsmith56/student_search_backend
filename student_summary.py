from __future__ import annotations

import argparse
import math
import random
import re
import sys
from pathlib import Path
from typing import Iterable

import time

import numpy as np
import language_tool_python
from rapidfuzz import fuzz

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from models.student import FullStudent
from repositories.students import get_all_full_students, get_full_student_by_id

SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
WORD_RE = re.compile(r"[A-Za-z0-9']+")
MAX_SENTENCE_CHARS = 700

_GRAMMAR_CLEAN_ENABLED = False
_NO_QUOTE_MODE = False
_GRAMMAR_TOOL: language_tool_python.LanguageTool | None = None
_GRAMMAR_TOOL_FAILED = False
_GRAMMAR_TOOL_WARNED = False


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


def _normalize_favorite_subjects(value: str | None) -> str:
    text = _clean_text(value).strip().strip("'\"")
    if text == "":
        return ""
    text = re.sub(r"^(?:my|our)\s+favorite\s+subjects?\s+are\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^favorite\s+subjects?\s*[:\-]\s*", "", text, flags=re.IGNORECASE)
    text = text.strip(" .,:;")
    return text


def _random_app_id() -> int | None:
    students = get_all_full_students()
    if not students:
        return None
    return int(random.choice(students).app_id)


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


def _light_cleanup_quote(text: str) -> str:
    cleaned = _clean_text(text)
    if cleaned == "":
        return ""
    cleaned = re.sub(
        r"thank you that you are thinking about",
        "thank you for thinking about",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\b(\d+)\s+Months\b", r"\1 months", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bi\b", "I", cleaned)
    cleaned = re.sub(r"\s+([,.!?])", r"\1", cleaned)
    cleaned = re.sub(r"([,.!?])(?=[A-Za-z])", r"\1 ", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned


def _get_grammar_tool() -> language_tool_python.LanguageTool | None:
    global _GRAMMAR_TOOL, _GRAMMAR_TOOL_FAILED, _GRAMMAR_TOOL_WARNED
    if not _GRAMMAR_CLEAN_ENABLED:
        return None
    if _GRAMMAR_TOOL is not None:
        return _GRAMMAR_TOOL
    if _GRAMMAR_TOOL_FAILED:
        return None

    try:
        _GRAMMAR_TOOL = language_tool_python.LanguageTool("en-US")
    except Exception as exc:
        _GRAMMAR_TOOL_FAILED = True
        if not _GRAMMAR_TOOL_WARNED:
            print(
                f"Grammar cleanup unavailable ({exc.__class__.__name__}: {exc}). Continuing without it.",
                file=sys.stderr,
            )
            _GRAMMAR_TOOL_WARNED = True
        return None
    return _GRAMMAR_TOOL


def _grammar_correct_quote(text: str) -> str:
    normalized = _normalize_quote(_light_cleanup_quote(text))
    if normalized == "" or not _GRAMMAR_CLEAN_ENABLED:
        return normalized

    tool = _get_grammar_tool()
    if tool is None:
        return normalized

    try:
        corrected = tool.correct(normalized).strip()
    except Exception:
        return normalized
    return _normalize_quote(corrected)


def _shutdown_grammar_tool() -> None:
    global _GRAMMAR_TOOL
    if _GRAMMAR_TOOL is None:
        return
    try:
        _GRAMMAR_TOOL.close()
    except Exception:
        pass
    _GRAMMAR_TOOL = None


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
    favorite_subjects = _normalize_favorite_subjects(student.favorite_subjects)
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
        score = (pref_score * 0.65) + (query_score * 0.35) + (min(len(sentence), 320) / 110)
        if score > best_score:
            best_sentence = sentence
            best_score = score
    return best_sentence, best_score


def _top_unique_quotes(pool: list[str], query: str, count: int = 3) -> list[str]:
    scored: list[tuple[float, str]] = []
    for sentence in pool:
        query_score = float(fuzz.token_set_ratio(sentence, query)) if query else 0.0
        score = query_score + (min(len(sentence), 320) / 100)
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
    if _NO_QUOTE_MODE:
        return " ".join([_facts_sentence(student), _interest_sentence(student)])

    subject = _subject_pronoun(student)
    final_student_quote = student_quote or f"{subject} is eager to learn from a host-family experience."
    final_student_quote = _grammar_correct_quote(final_student_quote)
    parts = [_facts_sentence(student), _interest_sentence(student), f"{subject} says: '{final_student_quote}'"]
    return " ".join(parts)


def _sentence_terms(sentence: str) -> list[str]:
    return [token.lower() for token in WORD_RE.findall(sentence) if len(token) > 1]


def _lexrank_extract(sentences: list[str], sentence_count: int = 2) -> list[str]:
    if not sentences:
        return []

    tokenized = [_sentence_terms(sentence) for sentence in sentences]
    sentence_sets = [tokens for tokens in tokenized if tokens]
    if not sentence_sets:
        return sentences[:sentence_count]

    n = len(sentences)
    tf_metrics: list[dict[str, float]] = []
    for tokens in tokenized:
        counts: dict[str, int] = {}
        for token in tokens:
            counts[token] = counts.get(token, 0) + 1
        max_tf = max(counts.values()) if counts else 1
        tf_metrics.append({term: tf / max_tf for term, tf in counts.items()})

    idf_metrics: dict[str, float] = {}
    for tokens in tokenized:
        unique_terms = set(tokens)
        for term in unique_terms:
            if term not in idf_metrics:
                n_j = sum(1 for sentence_tokens in tokenized if term in sentence_tokens)
                idf_metrics[term] = math.log(n / (1 + n_j)) if n > 0 else 0.0

    matrix = np.zeros((n, n), dtype=float)
    degrees = np.zeros((n,), dtype=float)
    threshold = 0.1

    for row in range(n):
        terms_row = set(tokenized[row])
        tf_row = tf_metrics[row]
        for col in range(n):
            terms_col = set(tokenized[col])
            tf_col = tf_metrics[col]
            common = terms_row & terms_col
            numerator = sum(tf_row.get(term, 0.0) * tf_col.get(term, 0.0) * (idf_metrics.get(term, 0.0) ** 2) for term in common)

            denom_row = sum((tf_row.get(term, 0.0) * idf_metrics.get(term, 0.0)) ** 2 for term in terms_row)
            denom_col = sum((tf_col.get(term, 0.0) * idf_metrics.get(term, 0.0)) ** 2 for term in terms_col)

            similarity = 0.0
            if denom_row > 0 and denom_col > 0:
                similarity = numerator / (math.sqrt(denom_row) * math.sqrt(denom_col))

            if similarity > threshold:
                matrix[row, col] = 1.0
                degrees[row] += 1.0

    for row in range(n):
        if degrees[row] == 0:
            degrees[row] = 1.0
        matrix[row, :] = matrix[row, :] / degrees[row]

    p = np.array([1.0 / n] * n, dtype=float)
    epsilon = 0.1
    delta = 1.0
    transposed = matrix.T
    while delta > epsilon:
        next_p = np.dot(transposed, p)
        norm = np.linalg.norm(next_p)
        if norm > 0:
            next_p = next_p / norm
        delta = np.linalg.norm(next_p - p)
        p = next_p

    ranked_indices = np.argsort(-p)[: min(sentence_count, n)]
    ranked_set = set(int(idx) for idx in ranked_indices)
    return [sentence for idx, sentence in enumerate(sentences) if idx in ranked_set]


def _lsa_extract(sentences: list[str], sentence_count: int = 2) -> list[str]:
    if not sentences:
        return []

    tokenized = [_sentence_terms(sentence) for sentence in sentences]
    vocab: dict[str, int] = {}
    for tokens in tokenized:
        for token in tokens:
            if token not in vocab:
                vocab[token] = len(vocab)

    if not vocab:
        return sentences[:sentence_count]

    term_sentence = np.zeros((len(vocab), len(sentences)), dtype=float)
    for col, tokens in enumerate(tokenized):
        for token in tokens:
            term_sentence[vocab[token], col] += 1.0

    if term_sentence.size == 0:
        return sentences[:sentence_count]

    _, singular_values, vt = np.linalg.svd(term_sentence, full_matrices=False)
    if len(singular_values) == 0:
        return sentences[:sentence_count]

    dimensions = max(1, min(3, len(singular_values)))
    salience = np.sqrt((vt[:dimensions, :] ** 2).sum(axis=0))
    ranked_indices = np.argsort(-salience)[: min(sentence_count, len(sentences))]
    ranked_set = set(int(idx) for idx in ranked_indices)
    return [sentence for idx, sentence in enumerate(sentences) if idx in ranked_set]


def _build_summary_with_algorithm(
    student: FullStudent,
    extract_fn,
    sentence_count: int = 2,
    parent_variant: int = 0,
) -> str:
    if _NO_QUOTE_MODE:
        return _render_summary_with_quotes(student, "")

    candidates = _candidate_sentences(student)
    if not candidates:
        student_quote, parent_quote = _select_quotes(student, [], parent_variant=parent_variant)
        if student_quote == "":
            student_quote = _normalize_quote(_highest_signal_sentence(student))
        return _render_summary_with_quotes(student, student_quote, parent_quote)

    summary_items = extract_fn(candidates, sentence_count=sentence_count)
    if not summary_items:
        summary_items = [_highest_signal_sentence(student)]

    cleaned: list[str] = []
    for sentence in summary_items:
        normalized = _normalize_quote(sentence)
        if normalized:
            cleaned.append(normalized)
    student_quote, parent_quote = _select_quotes(student, cleaned, parent_variant=parent_variant)
    if student_quote == "" and cleaned:
        student_quote = cleaned[0]
    return _render_summary_with_quotes(student, student_quote, parent_quote)


def build_Result1_lexrank(student: FullStudent) -> str:
    return _build_summary_with_algorithm(student, _lexrank_extract, parent_variant=2)


def build_Result2_lsa(student: FullStudent) -> str:
    return _build_summary_with_algorithm(student, _lsa_extract, parent_variant=3)


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
    parser.add_argument(
        "--appid",
        type=int,
        required=False,
        help="Student application id. If omitted, one is chosen at random.",
    )
    parser.add_argument(
        "--grammar-clean",
        action="store_true",
        help="Apply offline grammar cleanup to selected quotes using LanguageTool.",
    )
    parser.add_argument(
        "--no-quote",
        action="store_true",
        help="Omit the student quote and output only profile facts and interests.",
    )
    return parser.parse_args()


def main() -> int:
    global _GRAMMAR_CLEAN_ENABLED, _NO_QUOTE_MODE
    args = _parse_args()
    _GRAMMAR_CLEAN_ENABLED = bool(args.grammar_clean)
    _NO_QUOTE_MODE = bool(args.no_quote)
    app_id = args.appid if args.appid is not None else _random_app_id()
    if app_id is None:
        print("No FullStudent records found in student_full_view.")
        return 1
    if args.appid is None:
        print(f"No appid provided; randomly selected app_id={app_id}.")

    student = get_full_student_by_id(app_id)
    if student is None:
        print(f"No FullStudent found for app_id={app_id}.")
        return 1

    try:
        start = time.perf_counter()
        summary1 = build_Result1_lexrank(student)
        summary2 = build_Result2_lsa(student)
        end = time.perf_counter()
        print(f"Total tile after imports - {end-start}")
    except ValueError as exc:
        print(str(exc))
        return 1
    finally:
        _shutdown_grammar_tool()

    print("Student Summary (Result1 + Result2)")
    print(f"app_id={student.app_id} | first_name={student.first_name} | country={student.country}")
    print()
    print(f"Result1: {summary1}")
    print()
    print(f"Result2: {summary2}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
