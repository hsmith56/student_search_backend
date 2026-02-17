from __future__ import annotations

import argparse
import random
import re
import sys
from pathlib import Path
from typing import Iterable

import nltk
from rapidfuzz import fuzz
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sumy.nlp.tokenizers import Tokenizer
from sumy.parsers.plaintext import PlaintextParser
from sumy.summarizers.lex_rank import LexRankSummarizer
from sumy.summarizers.lsa import LsaSummarizer
from sumy.summarizers.luhn import LuhnSummarizer
from yake import KeywordExtractor

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from models.student import FullStudent
from repositories.students import get_all_full_students, get_full_student_by_id

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


def _narrative_blocks(student: FullStudent) -> list[str]:
    return [
        *_student_narrative_blocks(student),
        *_parent_narrative_blocks(student),
        *_other_narrative_blocks(student),
    ]


def _student_narrative_blocks(student: FullStudent) -> list[str]:
    return [
        student.intro_message,
        student.message_to_host_family,
    ]


def _parent_narrative_blocks(student: FullStudent) -> list[str]:
    return [
        student.message_from_natural_family,
    ]


def _other_narrative_blocks(student: FullStudent) -> list[str]:
    return [
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
    words = sentence.split()
    return len(words) >= 6


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


def _subject_pronoun(student: FullStudent) -> str:
    gender = _clean_text(student.gender_desc).lower()
    return "She" if "female" in gender else "He"


def _possessive_pronoun(student: FullStudent) -> str:
    gender = _clean_text(student.gender_desc).lower()
    return "Her" if "female" in gender else "His"


def _normalize_quote(sentence: str) -> str:
    cleaned = _clip_sentence(sentence).strip().strip("'\"")
    if cleaned == "":
        return ""
    if cleaned[-1] not in ".!?":
        cleaned += "."
    return cleaned


def _best_sentence_from_pool(
    pool: list[str], preferred: list[str], query: str
) -> tuple[str, float]:
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
    student_pool = _student_candidate_sentences(student)
    parent_pool = _parent_candidate_sentences(student)

    student_quotes = _top_unique_quotes(student_pool, query, count=quote_count)
    parent_quotes = _top_unique_quotes(parent_pool, query, count=quote_count)

    student_fallbacks = [
        "I am excited to learn from a new host-family environment.",
        "I hope to share my culture while adapting to daily life in the U.S.",
        "I want to grow through new experiences, school life, and community activities.",
    ]
    parent_fallbacks = [
        f"{student.first_name} is respectful and eager to participate in family life.",
        f"We are proud of {student.first_name}'s motivation for this exchange experience.",
        "We hope this year helps our child grow in independence and confidence.",
    ]

    for fallback in student_fallbacks:
        quote = _normalize_quote(fallback)
        if quote and all(fuzz.token_set_ratio(quote, existing) < 86 for existing in student_quotes):
            student_quotes.append(quote)
        if len(student_quotes) >= quote_count:
            break

    for fallback in parent_fallbacks:
        quote = _normalize_quote(fallback)
        if quote and all(fuzz.token_set_ratio(quote, existing) < 86 for existing in parent_quotes):
            parent_quotes.append(quote)
        if len(parent_quotes) >= quote_count:
            break

    return student_quotes[:quote_count], parent_quotes[:quote_count]


def _unique_quotes_in_order(quotes: list[str], max_count: int = 3) -> list[str]:
    unique: list[str] = []
    for raw in quotes:
        quote = _normalize_quote(raw)
        if quote == "":
            continue
        if any(fuzz.token_set_ratio(quote, existing) >= 90 for existing in unique):
            continue
        unique.append(quote)
        if len(unique) >= max_count:
            break
    return unique


def _quotes_from_results(
    result_summaries: list[str], quote_count: int = 3
) -> tuple[list[str], list[str]]:
    student_quotes: list[str] = []
    parent_quotes: list[str] = []
    for summary in result_summaries:
        student_quotes.extend(re.findall(r"(?:He|She) says:\s*'([^']+)'", summary))
        parent_quotes.extend(re.findall(r"(?:His|Her) parents say:\s*'([^']+)'", summary))

    return (
        _unique_quotes_in_order(student_quotes, max_count=quote_count),
        _unique_quotes_in_order(parent_quotes, max_count=quote_count),
    )


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
                [*student_quotes, preferred_quote],
                preferred,
                query,
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
        idx = parent_variant % len(parent_ranked)
        parent_quote = _normalize_quote(parent_ranked[idx])

    return student_quote, parent_quote


def _render_summary_with_quotes(
    student: FullStudent, student_quote: str, parent_quote: str = ""
) -> str:
    parts = [_facts_sentence(student), _interest_sentence(student)]
    subject = _subject_pronoun(student)
    possessive = _possessive_pronoun(student)
    final_student_quote = student_quote or f"{subject} is eager to learn from a host-family experience."
    parts.append(f"{subject} says: '{final_student_quote}'")
    if parent_quote:
        parts.append(f"{possessive} parents say: '{parent_quote}'")
    return " ".join(part for part in parts if part)


def _unique_best_sentences(candidates: list[tuple[float, str]], count: int = 2) -> list[str]:
    picked: list[str] = []
    for _, sentence in sorted(candidates, key=lambda pair: pair[0], reverse=True):
        if any(fuzz.token_set_ratio(sentence, existing) >= 88 for existing in picked):
            continue
        picked.append(_clip_sentence(sentence))
        if len(picked) >= count:
            break
    return picked


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
    interest_pool = [*student.selected_interests]
    unique_interests = list(dict.fromkeys(_clean_text(item) for item in interest_pool if _clean_text(item)))
    interests = unique_interests[:4]
    favorite_subjects = _clean_text(student.favorite_subjects)
    gpa = _to_float(student.gpa)
    subject = _subject_pronoun(student)
    possessive = _possessive_pronoun(student).lower()

    interests_text = ""
    if interests and favorite_subjects:
        interests_text = (
            f"{subject} highlights interests in {_join_human(interests)} and describes {possessive} favorite subjects as {favorite_subjects}."
        )
    elif interests:
        interests_text = f"{subject} highlights interests in {_join_human(interests)}."
    elif favorite_subjects:
        interests_text = f"{subject} describes {possessive} favorite subjects as {favorite_subjects}."
    elif gpa is not None:
        interests_text = f"{possessive.capitalize()} profile lists a GPA of {gpa:.2f}."
    else:
        interests_text = f"{possessive.capitalize()} placement status is currently {student.placement_status}."

    return interests_text


def _build_summary_result1(student: FullStudent) -> str:
    preferred = [_highest_signal_sentence(student)]
    student_quote, parent_quote = _select_quotes(student, preferred, parent_variant=0)
    if student_quote == "":
        subject = _subject_pronoun(student)
        student_quote = (
            f"{subject} is excited to contribute positively to a host-family home."
        )
    return _render_summary_with_quotes(student, student_quote, parent_quote)


def _build_summary_result2_yake(student: FullStudent) -> str:
    candidates = _candidate_sentences(student)
    if not candidates:
        student_quote, parent_quote = _select_quotes(student, [], parent_variant=1)
        if student_quote == "":
            student_quote = _normalize_quote(_highest_signal_sentence(student))
        return _render_summary_with_quotes(student, student_quote, parent_quote)

    profile_text = " ".join(_narrative_blocks(student) + student.selected_interests)
    keyword_extractor = KeywordExtractor(lan="en", n=2, top=10, dedupLim=0.85)
    keywords = keyword_extractor.extract_keywords(profile_text)
    if not keywords:
        fallback = _normalize_quote(_highest_signal_sentence(student))
        student_quote, parent_quote = _select_quotes(student, [fallback], parent_variant=1)
        if student_quote == "":
            student_quote = fallback
        return _render_summary_with_quotes(student, student_quote, parent_quote)

    keyword_scores = {keyword.lower(): 1.0 / (score + 1e-9) for keyword, score in keywords}
    scored: list[tuple[float, str]] = []
    for sentence in candidates:
        lower = sentence.lower()
        sentence_score = sum(weight for keyword, weight in keyword_scores.items() if keyword in lower)
        sentence_score += min(len(sentence), 180) / 90
        scored.append((sentence_score, sentence))

    selected = _unique_best_sentences(scored, count=2)
    if not selected:
        selected = [_normalize_quote(_highest_signal_sentence(student))]

    student_quote, parent_quote = _select_quotes(student, selected, parent_variant=1)
    if student_quote == "":
        student_quote = _normalize_quote(selected[0])
    return _render_summary_with_quotes(student, student_quote, parent_quote)


def _ensure_nltk_data() -> None:
    for resource in ("punkt", "punkt_tab"):
        try:
            nltk.data.find(f"tokenizers/{resource}")
        except LookupError:
            nltk.download(resource, quiet=True)


def _build_summary_result3_lexrank(student: FullStudent) -> str:
    candidates = _candidate_sentences(student)
    if not candidates:
        student_quote, parent_quote = _select_quotes(student, [], parent_variant=2)
        if student_quote == "":
            student_quote = _normalize_quote(_highest_signal_sentence(student))
        return _render_summary_with_quotes(student, student_quote, parent_quote)

    _ensure_nltk_data()
    corpus = "\n".join(candidates)
    parser = PlaintextParser.from_string(corpus, Tokenizer("english"))
    summarizer = LexRankSummarizer()
    summary_items = [str(sentence) for sentence in summarizer(parser.document, 2)]

    if not summary_items:
        summary_items = [_highest_signal_sentence(student)]

    cleaned = [_normalize_quote(sentence) for sentence in summary_items if _normalize_quote(sentence)]
    student_quote, parent_quote = _select_quotes(student, cleaned, parent_variant=2)
    if student_quote == "" and cleaned:
        student_quote = cleaned[0]
    return _render_summary_with_quotes(student, student_quote, parent_quote)


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

    cleaned = [_normalize_quote(sentence) for sentence in summary_items if _normalize_quote(sentence)]
    student_quote, parent_quote = _select_quotes(
        student, cleaned, parent_variant=parent_variant
    )
    if student_quote == "" and cleaned:
        student_quote = cleaned[0]
    return _render_summary_with_quotes(student, student_quote, parent_quote)


def _build_summary_result4_lsa(student: FullStudent) -> str:
    return _build_summary_with_sumy(student, LsaSummarizer(), parent_variant=3)


def _build_summary_result5_luhn(student: FullStudent) -> str:
    return _build_summary_with_sumy(student, LuhnSummarizer(), parent_variant=4)


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


def _build_summary_result6_tfidf_mmr(student: FullStudent) -> str:
    candidates = _candidate_sentences(student)
    if not candidates:
        student_quote, parent_quote = _select_quotes(student, [], parent_variant=5)
        if student_quote == "":
            student_quote = _normalize_quote(_highest_signal_sentence(student))
        return _render_summary_with_quotes(student, student_quote, parent_quote)

    query = _context_query(student)
    if query == "":
        fallback = _highest_signal_sentence(student)
        student_quote, parent_quote = _select_quotes(student, [fallback], parent_variant=5)
        if student_quote == "":
            student_quote = _normalize_quote(fallback)
        return _render_summary_with_quotes(student, student_quote, parent_quote)

    docs = [*candidates, query]
    try:
        vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
        matrix = vectorizer.fit_transform(docs)
    except ValueError:
        fallback = _highest_signal_sentence(student)
        student_quote, parent_quote = _select_quotes(student, [fallback], parent_variant=5)
        if student_quote == "":
            student_quote = _normalize_quote(fallback)
        return _render_summary_with_quotes(student, student_quote, parent_quote)

    sentence_vectors = matrix[:-1]
    query_vector = matrix[-1]
    relevance = cosine_similarity(sentence_vectors, query_vector).ravel()
    similarity = cosine_similarity(sentence_vectors)

    top_k = min(2, len(candidates))
    lambda_weight = 0.72
    selected: list[int] = []
    remaining = list(range(len(candidates)))

    while remaining and len(selected) < top_k:
        best_idx = remaining[0]
        best_score = -1e9
        for idx in remaining:
            redundancy = max((similarity[idx, j] for j in selected), default=0.0)
            mmr_score = (lambda_weight * relevance[idx]) - ((1 - lambda_weight) * redundancy)
            if mmr_score > best_score:
                best_score = mmr_score
                best_idx = idx
        selected.append(best_idx)
        remaining.remove(best_idx)

    selected_sentences = [_clip_sentence(candidates[idx]) for idx in selected]
    selected_sentences = [sentence for sentence in selected_sentences if sentence]
    if not selected_sentences:
        selected_sentences = [_normalize_quote(_highest_signal_sentence(student))]

    student_quote, parent_quote = _select_quotes(
        student, selected_sentences, parent_variant=5
    )
    if student_quote == "":
        student_quote = _normalize_quote(selected_sentences[0])
    return _render_summary_with_quotes(student, student_quote, parent_quote)


def _build_consensus_summary(student: FullStudent, summaries: list[str]) -> str:
    student_quotes: list[str] = []
    parent_quotes: list[str] = []
    for summary in summaries:
        student_quotes.extend(re.findall(r"(?:He|She) says:\s*'([^']+)'", summary))
        parent_quotes.extend(re.findall(r"(?:His|Her) parents say:\s*'([^']+)'", summary))

    def pick_consensus_quote(quotes: list[str]) -> str:
        if not quotes:
            return ""

        query = _context_query(student)
        reps: list[str] = []
        supports: list[int] = []
        relevance_scores: list[list[float]] = []

        for raw in quotes:
            quote = _normalize_quote(raw)
            if quote == "":
                continue

            matched_idx = -1
            for idx, rep in enumerate(reps):
                if fuzz.token_set_ratio(quote, rep) >= 84:
                    matched_idx = idx
                    break

            relevance = float(fuzz.token_set_ratio(quote, query)) / 100 if query else 0.0

            if matched_idx == -1:
                reps.append(quote)
                supports.append(1)
                relevance_scores.append([relevance])
                continue

            supports[matched_idx] += 1
            relevance_scores[matched_idx].append(relevance)
            if fuzz.token_set_ratio(quote, query) > fuzz.token_set_ratio(reps[matched_idx], query):
                reps[matched_idx] = quote

        if not reps:
            return ""

        ranked = []
        for idx, rep in enumerate(reps):
            avg_rel = sum(relevance_scores[idx]) / len(relevance_scores[idx])
            score = (supports[idx] * 2.0) + avg_rel + (min(len(rep), 160) / 500)
            ranked.append((score, rep, supports[idx]))
        ranked.sort(key=lambda item: (item[2], item[0]), reverse=True)
        return ranked[0][1]

    student_quote = pick_consensus_quote(student_quotes)
    parent_quote = pick_consensus_quote(parent_quotes)
    if student_quote == "":
        student_quote = _normalize_quote(_highest_signal_sentence(student))
    return _render_summary_with_quotes(student, student_quote, parent_quote)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate multi-approach summaries for a FullStudent profile."
    )
    parser.add_argument(
        "--appid",
        type=int,
        default=None,
        help="Use a specific student app_id instead of selecting a random student.",
    )
    parser.add_argument(
        "--quotes",
        action="store_true",
        help="Output only quote candidates for the selected student.",
    )
    parser.add_argument(
        "--quotes-n",
        type=int,
        default=3,
        help="Number of quotes to output per side when using --quotes (default: 3).",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    student: FullStudent | None
    if args.appid is not None:
        student = get_full_student_by_id(args.appid)
        if student is None:
            print(f"No FullStudent found for app_id={args.appid}.")
            return 1
    else:
        students = get_all_full_students()
        if not students:
            print("No FullStudent records found in student_full_view.")
            return 1
        student = random.choice(students)

    if args.quotes:
        quotes_n = max(1, int(args.quotes_n))
        result1 = _build_summary_result1(student)
        result2 = _build_summary_result2_yake(student)
        result3 = _build_summary_result3_lexrank(student)
        result4 = _build_summary_result4_lsa(student)
        result5 = _build_summary_result5_luhn(student)
        result6 = _build_summary_result6_tfidf_mmr(student)
        student_quotes, parent_quotes = _quotes_from_results(
            [result1, result2, result3, result4, result5, result6],
            quote_count=quotes_n,
        )
        print(f"Student/Parent Quotes ({quotes_n} each)")
        print(f"app_id={student.app_id} | first_name={student.first_name} | country={student.country}")
        print()
        print("student_quotes:")
        for idx, quote in enumerate(student_quotes, start=1):
            print(f"{idx}. {quote}")
        print()
        print("parent_quotes:")
        for idx, quote in enumerate(parent_quotes, start=1):
            print(f"{idx}. {quote}")
        return 0

    result1 = _build_summary_result1(student)
    result2 = _build_summary_result2_yake(student)
    result3 = _build_summary_result3_lexrank(student)
    result4 = _build_summary_result4_lsa(student)
    result5 = _build_summary_result5_luhn(student)
    result6 = _build_summary_result6_tfidf_mmr(student)
    consensus = _build_consensus_summary(
        student,
        [result1, result2, result3, result4, result5, result6],
    )

    print("Random FullStudent Summary (1 example, 6 approaches + consensus)")
    print(f"app_id={student.app_id} | first_name={student.first_name} | country={student.country}")
    print()
    print(f"result1: {result1}")
    print()
    print(f"result2: {result2}")
    print()
    print(f"result3: {result3}")
    print()
    print(f"result4: {result4}")
    print()
    print(f"result5: {result5}")
    print()
    print(f"result6: {result6}")
    print()
    print(f"consensus: {consensus}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
