from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass
from statistics import mean
from typing import Any

from core.config import settings
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

import spacy


@dataclass
class Candidate:
    score: int
    app_id: int
    first_name: str
    country: str
    program_type: str
    reasons: list[str]


TEXT_FIELDS = (
    "free_text_interests",
    # "family_description",
    "favorite_subjects",
    "photo_comments",
    # "intro_message",
    # "message_to_host_family",
    # "message_from_natural_family",
)

DOMAIN_STOP_WORDS = {
    "host",
    "family",
    "student",
    "students",
    "school",
    "exchange",
    "year",
    "years",
    "old",
    "would",
    "like",
    "also",
    "really",
    "get",
    "going",
    "boy",
    "girl",
    "town",
    "board",
    "mom",
    "mother",
    "dad",
    "father",
    "sister",
    "brother",
    "does",
    "doesn",
    "dont",
    "didnt",
    "cant",
    "im",
    "ive",
}


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


def get_last_n_placed_students(
    conn: sqlite3.Connection, n: int
) -> tuple[list[sqlite3.Row], list[int], list[int]]:
    if n <= 0:
        return [], [], []

    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT app_id
        FROM placement_metrics
        WHERE placementDate IS NOT NULL AND TRIM(placementDate) != ''
        ORDER BY placementDate DESC
        LIMIT ?
        """,
        (n,),
    )
    app_ids = [int(row[0]) for row in cursor.fetchall()]
    students = get_students_by_app_ids(conn, app_ids)
    resolved_ids = [int(row["app_id"]) for row in students]
    unresolved_ids = sorted(set(app_ids) - set(resolved_ids))
    return students, app_ids, unresolved_ids


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

    top_interests = [
        name
        for name, count in interests.most_common()
        if count >= max(2, baseline_size // 3)
    ][:5]

    baseline = {
        "country": countries.most_common(1)[0][0] if countries else None,
        "gender": genders.most_common(1)[0][0] if genders else None,
        "program_type": programs.most_common(1)[0][0] if programs else None,
        "gpa_floor": round(mean(gpas), 2) if gpas else None,
        "age_floor": round(mean(ages)) if ages else None,
        "single_placement": single_true >= max(1, baseline_size // 2),
        "double_placement": double_true >= max(1, baseline_size // 2),
        "pets_in_home": "yes" if pets_true >= max(1, baseline_size // 2) else "all",
        "has_video": has_video >= max(1, baseline_size // 2),
        "top_interests": top_interests,
    }

    diagnostics = {
        "country_counts": countries,
        "gender_counts": genders,
        "program_counts": programs,
        "interest_counts": interests,
    }
    return baseline, diagnostics


def row_text_blob(row: sqlite3.Row) -> str:
    parts: list[str] = []
    for field in TEXT_FIELDS:
        value = row[field]
        if field == "free_text_interests":
            parts.extend(parse_json_list(value))
            continue
        if value not in (None, ""):
            parts.append(str(value))
    return " ".join(parts)


def clean_text_for_tfidf(text: str) -> str:
    value = text.lower()
    value = re.sub(r"n['’]t\b", " not", value)
    value = re.sub(r"['’]re\b", " are", value)
    value = re.sub(r"['’]ve\b", " have", value)
    value = re.sub(r"['’]ll\b", " will", value)
    value = re.sub(r"['’]d\b", " would", value)
    value = re.sub(r"[^a-z\s]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def normalize_stop_words(words: set[str]) -> list[str]:
    normalized: set[str] = set()
    for word in words:
        cleaned = clean_text_for_tfidf(str(word))
        if cleaned == "":
            continue
        for token in cleaned.split():
            if token != "":
                normalized.add(token)
    return sorted(normalized)


def derive_spacy_only_commonalities(
    favorites: list[sqlite3.Row],
) -> tuple[dict[str, Any], dict[str, Any]]:
    # Standalone spaCy-only analysis: favorites corpus only, no TF-IDF/corpus contrast.
    text_fields = TEXT_FIELDS
 

    local_stop_words = {
        "host",
        "family",
        "student",
        "students",
        "school",
        "exchange",
        "would",
        "also",
        "really",
        "like",
        "year",
        "years",
    }

    try:
        nlp = spacy.load("en_core_web_sm", disable=["parser", "ner", "textcat"])
        spacy_model = "en_core_web_sm"
    except Exception:
        nlp = spacy.blank("en")
        spacy_model = "blank_en"

    token_counts = Counter()
    phrase_counts = Counter()
    doc_frequency = Counter()

    for row in favorites:
        doc_parts: list[str] = []
        for field in text_fields:
            value = row[field]
            if field == "free_text_interests":
                if isinstance(value, str):
                    try:
                        parsed = json.loads(value)
                        if isinstance(parsed, list):
                            doc_parts.extend(str(item) for item in parsed if item not in (None, ""))
                    except json.JSONDecodeError:
                        pass
                continue
            if value not in (None, ""):
                doc_parts.append(str(value))

        doc_text = " ".join(doc_parts).strip()
        if doc_text == "":
            continue

        doc = nlp(doc_text)
        filtered_tokens: list[str] = []
        per_doc_token_set: set[str] = set()

        for token in doc:
            if token.is_space or token.is_punct:
                continue
            if token.like_num:
                continue

            raw = token.text.lower().strip()
            if raw == "":
                continue
            if len(raw) < 3:
                continue
            if raw in local_stop_words:
                continue
            if raw in nlp.Defaults.stop_words:
                continue

            lemma = token.lemma_.lower().strip() if token.lemma_ else raw
            if lemma == "" or lemma == "-pron-":
                lemma = raw
            if len(lemma) < 3:
                continue
            if lemma in local_stop_words:
                continue
            if lemma in nlp.Defaults.stop_words:
                continue

            filtered_tokens.append(lemma)
            per_doc_token_set.add(lemma)

        token_counts.update(filtered_tokens)
        doc_frequency.update(per_doc_token_set)
        for i in range(len(filtered_tokens) - 1):
            phrase = f"{filtered_tokens[i]} {filtered_tokens[i + 1]}"
            phrase_counts[phrase] += 1

    min_docs = max(2, len(favorites) // 2)
    common_terms = [term for term, count in doc_frequency.most_common() if count >= min_docs][:25]
    common_phrases = [phrase for phrase, count in phrase_counts.most_common() if count >= min_docs][:20]

    baseline = {
        "common_terms": common_terms,
        "common_phrases": common_phrases,
    }
    diagnostics = {
        "model": spacy_model,
        "min_favorite_docs": min_docs,
        "token_counts": token_counts,
        "doc_frequency": doc_frequency,
        "phrase_counts": phrase_counts,
    }
    return baseline, diagnostics


def derive_favorite_interest_profile(favorites: list[sqlite3.Row]) -> Counter:
    interests = Counter()
    for row in favorites:
        for item in parse_json_list(row["selected_interests"]):
            normalized = str(item).strip()
            if normalized != "":
                interests[normalized] += 1
    return interests


def score_candidates_spacy_engine(
    all_students: list[sqlite3.Row],
    favorites: list[sqlite3.Row],
    spacy_baseline: dict[str, Any],
    favorite_interests: Counter,
) -> list[Candidate]:
    favorite_ids = {int(row["app_id"]) for row in favorites}
    common_terms = set(str(x).lower() for x in spacy_baseline.get("common_terms", []))
    common_phrases = [str(x).lower() for x in spacy_baseline.get("common_phrases", [])]

    min_interest_docs = max(2, len(favorites) // 2)
    top_interests = {
        interest
        for interest, count in favorite_interests.items()
        if count >= min_interest_docs
    }

    ranked: list[Candidate] = []
    for row in all_students:
        app_id = int(row["app_id"])
        if app_id in favorite_ids:
            continue

        cleaned_text = clean_text_for_tfidf(row_text_blob(row))
        if cleaned_text == "":
            cleaned_words: set[str] = set()
        else:
            cleaned_words = set(cleaned_text.split())

        term_overlap = sorted(cleaned_words.intersection(common_terms))
        phrase_overlap = [phrase for phrase in common_phrases if phrase in cleaned_text]

        row_interests = {
            str(x).strip()
            for x in parse_json_list(row["selected_interests"])
            if str(x).strip() != ""
        }
        interest_overlap = sorted(row_interests.intersection(top_interests))

        score = 0
        if term_overlap:
            score += min(12, len(term_overlap) * 2)
        if phrase_overlap:
            score += min(12, len(phrase_overlap) * 3)
        if interest_overlap:
            score += min(12, len(interest_overlap) * 4)

        if score == 0:
            continue

        reasons: list[str] = []
        if term_overlap:
            reasons.append(f"spaCy term overlap: {', '.join(term_overlap[:5])}")
        if phrase_overlap:
            reasons.append(f"spaCy phrase overlap: {', '.join(phrase_overlap[:4])}")
        if interest_overlap:
            reasons.append(f"favorite-interest overlap: {', '.join(interest_overlap[:4])}")

        ranked.append(
            Candidate(
                score=score,
                app_id=app_id,
                first_name=str(row["first_name"] or ""),
                country=str(row["country"] or ""),
                program_type=str(row["program_type"] or ""),
                reasons=reasons,
            )
        )

    ranked.sort(key=lambda item: (-item.score, item.app_id))
    return ranked


def build_spacy_tokenizer(stop_words: set[str]):
    if spacy is None:
        raise RuntimeError(
            "spaCy is not installed. Install it with `uv add spacy` and try again."
        )
    nlp = spacy.blank("en")
    spacy_stop_words = {clean_text_for_tfidf(w) for w in nlp.Defaults.stop_words}
    effective_stop_words = set(stop_words).union(spacy_stop_words)

    def tokenizer(text: str) -> list[str]:
        cleaned = clean_text_for_tfidf(text)
        doc = nlp.make_doc(cleaned)
        tokens: list[str] = []
        for token in doc:
            value = token.text.strip()
            if value == "":
                continue
            if len(value) < 3:
                continue
            if value in effective_stop_words:
                continue
            tokens.append(value)
        return tokens

    return tokenizer


def derive_text_baseline(
    favorites: list[sqlite3.Row], all_students: list[sqlite3.Row], use_spacy: bool = False
) -> tuple[dict[str, Any], dict[str, Any]]:
    favorite_ids = {int(row["app_id"]) for row in favorites}
    corpus_ids: list[int] = []
    corpus_docs: list[str] = []

    for row in all_students:
        doc = row_text_blob(row).strip()
        if doc == "":
            continue
        corpus_ids.append(int(row["app_id"]))
        corpus_docs.append(doc)

    if not corpus_docs:
        return {"common_terms": [], "common_phrases": []}, {"distinctive_features": []}

    name_stop_words = {
        str(row["first_name"]).strip().lower()
        for row in all_students
        if row["first_name"] not in (None, "") and len(str(row["first_name"]).strip()) >= 3
    }
    all_stop_words_list = normalize_stop_words(
        set(ENGLISH_STOP_WORDS).union(DOMAIN_STOP_WORDS, name_stop_words)
    )
    all_stop_words = set(all_stop_words_list)

    vectorizer_kwargs: dict[str, Any] = {
        "ngram_range": (1, 2),
        "min_df": 2,
        "max_df": 0.7,
        "sublinear_tf": True,
    }
    tokenizer_mode = "default"
    if use_spacy:
        vectorizer_kwargs["tokenizer"] = build_spacy_tokenizer(all_stop_words)
        vectorizer_kwargs["preprocessor"] = None
        vectorizer_kwargs["token_pattern"] = None
        vectorizer_kwargs["lowercase"] = False
        tokenizer_mode = "spacy"
    else:
        vectorizer_kwargs["preprocessor"] = clean_text_for_tfidf
        vectorizer_kwargs["stop_words"] = all_stop_words_list

    vectorizer = TfidfVectorizer(**vectorizer_kwargs)
    corpus_matrix = vectorizer.fit_transform(corpus_docs)
    feature_names = vectorizer.get_feature_names_out()

    favorite_rows = [idx for idx, app_id in enumerate(corpus_ids) if app_id in favorite_ids]
    non_favorite_rows = [idx for idx, app_id in enumerate(corpus_ids) if app_id not in favorite_ids]

    if not favorite_rows:
        return {"common_terms": [], "common_phrases": []}, {"distinctive_features": []}

    favorite_matrix = corpus_matrix[favorite_rows]
    favorite_profile = favorite_matrix.mean(axis=0).A

    mean_favorite = favorite_profile.ravel()
    if non_favorite_rows:
        mean_non_favorite = corpus_matrix[non_favorite_rows].mean(axis=0).A1
    else:
        mean_non_favorite = mean_favorite * 0

    distinctiveness = mean_favorite - mean_non_favorite
    ranked_indices = distinctiveness.argsort()[::-1]

    distinctive_features: list[tuple[str, float, float, float]] = []
    min_favorite_docs = max(2, len(favorite_rows) // 2)
    favorite_presence = (favorite_matrix > 0).sum(axis=0).A1
    for idx in ranked_indices:
        gain = float(distinctiveness[idx])
        if gain <= 0:
            break
        if int(favorite_presence[idx]) < min_favorite_docs:
            continue
        term = str(feature_names[idx])
        distinctive_features.append(
            (
                term,
                gain,
                float(mean_favorite[idx]),
                float(mean_non_favorite[idx]),
            )
        )
        if len(distinctive_features) >= 40:
            break

    common_terms = [term for term, *_ in distinctive_features if " " not in term][:20]
    common_phrases = [term for term, *_ in distinctive_features if " " in term][:20]

    baseline = {
        "common_terms": common_terms,
        "common_phrases": common_phrases,
        "vectorizer": vectorizer,
        "corpus_ids": corpus_ids,
        "corpus_matrix": corpus_matrix,
        "favorite_profile": favorite_profile,
        "distinctive_features": distinctive_features,
        "stop_word_count": len(all_stop_words_list),
        "min_favorite_docs": min_favorite_docs,
        "tokenizer_mode": tokenizer_mode,
    }
    diagnostics = {
        "distinctive_features": distinctive_features,
        "stop_word_count": len(all_stop_words_list),
        "min_favorite_docs": min_favorite_docs,
        "tokenizer_mode": tokenizer_mode,
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
    if baseline["single_placement"]:
        payload["single_placement"] = "yes"
    if baseline["double_placement"]:
        payload["double_placement"] = "yes"
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
            if gpa is not None and baseline["gpa_floor"] is not None and gpa >= baseline["gpa_floor"]:
                score += 1
                reasons.append("gpa at/above baseline")
        except (TypeError, ValueError):
            pass

        try:
            age = int(row["adjusted_age"]) if row["adjusted_age"] is not None else None
            if age is not None and baseline["age_floor"] is not None and age >= baseline["age_floor"]:
                score += 1
                reasons.append("age at/above baseline")
        except (TypeError, ValueError):
            pass

        if baseline["single_placement"] and to_bool(row["single_placement"]):
            score += 1
            reasons.append("single placement")
        if baseline["double_placement"] and to_bool(row["double_placement"]):
            score += 1
            reasons.append("double placement")
        if baseline["pets_in_home"] == "yes" and to_bool(row["live_with_pets"]):
            score += 1
            reasons.append("pets in home")
        if baseline["has_video"] and str(row["media_link"] or "").strip() != "":
            score += 1
            reasons.append("has video")

        student_interests = set(parse_json_list(row["selected_interests"]))
        overlap = sorted(student_interests.intersection(top_interests))
        if overlap:
            score += min(3, len(overlap))
            reasons.append(f"interest overlap: {', '.join(overlap)}")

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
            )
        )

    ranked.sort(key=lambda item: (-item.score, item.app_id))
    return ranked


def score_candidates_text_only(
    all_students: list[sqlite3.Row],
    favorites: list[sqlite3.Row],
    text_baseline: dict[str, Any],
) -> list[Candidate]:
    favorite_ids = {int(row["app_id"]) for row in favorites}
    vectorizer: TfidfVectorizer | None = text_baseline.get("vectorizer")
    corpus_ids: list[int] = text_baseline.get("corpus_ids", [])
    corpus_matrix = text_baseline.get("corpus_matrix")
    favorite_profile = text_baseline.get("favorite_profile")
    distinctive_features: list[tuple[str, float, float, float]] = text_baseline.get(
        "distinctive_features", []
    )
    if vectorizer is None or corpus_matrix is None or favorite_profile is None:
        return []

    feature_index = vectorizer.vocabulary_
    top_explanatory = [term for term, *_ in distinctive_features[:25]]
    app_id_to_row = {int(row["app_id"]): row for row in all_students}

    ranked: list[Candidate] = []
    for idx, app_id in enumerate(corpus_ids):
        if app_id in favorite_ids:
            continue

        row = app_id_to_row.get(app_id)
        if row is None:
            continue

        vector = corpus_matrix[idx]
        similarity = float(cosine_similarity(vector, favorite_profile)[0][0])
        if similarity <= 0:
            continue

        score = int(round(similarity * 100))
        reasons: list[str] = []
        reasons.append(f"tf-idf similarity to favorite corpus: {similarity:.3f}")

        overlap: list[str] = []
        for term in top_explanatory:
            col = feature_index.get(term)
            if col is None:
                continue
            if vector[0, col] > 0:
                overlap.append(term)
        if overlap:
            reasons.append(f"distinctive overlap: {', '.join(overlap[:5])}")

        ranked.append(
            Candidate(
                score=score,
                app_id=app_id,
                first_name=str(row["first_name"] or ""),
                country=str(row["country"] or ""),
                program_type=str(row["program_type"] or ""),
                reasons=reasons,
            )
        )

    ranked.sort(key=lambda item: (-item.score, item.app_id))
    return ranked


def combine_candidate_lists(
    structured: list[Candidate],
    text_only: list[Candidate],
) -> list[Candidate]:
    by_structured = {candidate.app_id: candidate for candidate in structured}
    by_text = {candidate.app_id: candidate for candidate in text_only}
    all_ids = set(by_structured.keys()).union(by_text.keys())

    max_structured = max((candidate.score for candidate in structured), default=1)
    max_text = max((candidate.score for candidate in text_only), default=1)

    combined: list[Candidate] = []
    for app_id in all_ids:
        structured_candidate = by_structured.get(app_id)
        text_candidate = by_text.get(app_id)

        structured_norm = (
            structured_candidate.score / max_structured if structured_candidate is not None else 0.0
        )
        text_norm = text_candidate.score / max_text if text_candidate is not None else 0.0
        combined_score = int(round(((structured_norm + text_norm) / 2.0) * 100))

        source = structured_candidate if structured_candidate is not None else text_candidate
        if source is None:
            continue

        reasons: list[str] = []
        if structured_candidate is not None:
            reasons.append(f"structured score={structured_candidate.score}")
        if text_candidate is not None:
            reasons.append(f"text score={text_candidate.score}")
        if structured_candidate is not None:
            reasons.extend(structured_candidate.reasons[:2])
        if text_candidate is not None:
            reasons.extend(text_candidate.reasons[:2])

        combined.append(
            Candidate(
                score=combined_score,
                app_id=source.app_id,
                first_name=source.first_name,
                country=source.country,
                program_type=source.program_type,
                reasons=reasons,
            )
        )

    combined.sort(key=lambda item: (-item.score, item.app_id))
    return combined


def print_counter(counter: Counter, title: str, top_n: int = 5) -> None:
    print(f"\n{title}")
    if not counter:
        print("  - none")
        return
    for key, count in counter.most_common(top_n):
        print(f"  - {key}: {count}")


def run(
    username: str | None,
    top_n: int,
    text_only: bool,
    norec: bool,
    combined: bool,
    compare: str,
    use_spacy: bool,
    spacy_only: bool,
    spacy_engine: bool,
    last_n_placed: int | None,
) -> int:
    conn = get_connection()
    try:
        user = get_target_user(conn, username)
        if user is None:
            print("No matching user found.")
            return 1

        print("Recommendation POC")
        baseline_source = "favorites"
        requested_ids: list[int] = []
        unresolved: list[int] = []

        if last_n_placed is not None:
            if last_n_placed <= 0:
                print("--last-n-placed must be greater than 0")
                return 1
            baseline_source = f"placement_metrics:last_{last_n_placed}_placed"
            favorite_students, requested_ids, unresolved = get_last_n_placed_students(
                conn, last_n_placed
            )
            print(f"Baseline source: {baseline_source}")
            print(f"Requested app_ids from placement_metrics: {len(requested_ids)}")
        else:
            favorites_raw = parse_json_list(user["favorites"])
            favorite_ids = [int(item) for item in favorites_raw if str(item).isdigit()]
            requested_ids = favorite_ids
            favorite_students = get_students_by_app_ids(conn, favorite_ids)
            unresolved = sorted(
                set(favorite_ids) - {int(row["app_id"]) for row in favorite_students}
            )
            print(f"User: {user['username']} ({user['first_name']})")
            print(f"Baseline source: {baseline_source}")
            print(f"Favorite app_ids in user profile: {len(favorite_ids)}")

        all_students = get_all_students(conn)
        scoped_students = filter_students_by_compare_scope(all_students, compare)

        print(f"Baseline app_ids resolved in student_full_view: {len(favorite_students)}")
        print(
            f"Compare scope: {compare} | corpus size in scope: {len(scoped_students)}"
        )
        if unresolved:
            print(f"Unresolved baseline app_ids (not currently in full view): {unresolved}")

        if not favorite_students:
            print("No favorite students available to derive recommendations.")
            return 1

        if spacy_only:
            baseline, diagnostics = derive_spacy_only_commonalities(favorite_students)
            print("\nSpaCy-only commonality baseline (favorites only)")
            print(f"  - model: {diagnostics['model']}")
            print(f"  - min_favorite_docs: {diagnostics['min_favorite_docs']}")
            print(f"  - common_terms: {baseline['common_terms']}")
            print(f"  - common_phrases: {baseline['common_phrases']}")
            print_counter(diagnostics["doc_frequency"], "SpaCy favorites doc frequency", top_n=20)
            print_counter(diagnostics["phrase_counts"], "SpaCy favorites phrase frequency", top_n=20)
            return 0
        if spacy_engine:
            spacy_baseline, spacy_diagnostics = derive_spacy_only_commonalities(favorite_students)
            interest_profile = derive_favorite_interest_profile(favorite_students)
            min_interest_docs = max(2, len(favorite_students) // 2)
            top_interest_signals = [
                interest for interest, count in interest_profile.items() if count >= min_interest_docs
            ]

            print("\nSpaCy recommendation engine")
            print(f"  - model: {spacy_diagnostics['model']}")
            print(f"  - common_terms: {spacy_baseline['common_terms']}")
            print(f"  - common_phrases: {spacy_baseline['common_phrases']}")
            print(f"  - top_favorite_interests: {top_interest_signals}")
            if norec:
                return 0

            ranked = score_candidates_spacy_engine(
                scoped_students, favorite_students, spacy_baseline, interest_profile
            )
        elif combined:
            structured_baseline, structured_diagnostics = derive_baseline(favorite_students)
            payload = build_search_filter_payload(structured_baseline)
            text_baseline, text_diagnostics = derive_text_baseline(
                favorite_students, scoped_students, use_spacy=use_spacy
            )

            print("\nCombined mode: structured + text analysis")
            print("\nDerived baseline")
            for key in [
                "country",
                "gender",
                "program_type",
                "gpa_floor",
                "age_floor",
                "single_placement",
                "double_placement",
                "pets_in_home",
                "has_video",
                "top_interests",
            ]:
                print(f"  - {key}: {structured_baseline[key]}")
            print_counter(structured_diagnostics["country_counts"], "Favorite countries")
            print_counter(structured_diagnostics["gender_counts"], "Favorite genders")
            print_counter(structured_diagnostics["program_counts"], "Favorite program types")
            print_counter(
                structured_diagnostics["interest_counts"], "Top favorite interests", top_n=10
            )
            print("\nSearchFilters-style payload candidate")
            print(json.dumps(payload, indent=2))

            print("\nText-only commonality baseline")
            print(f"  - common_terms: {text_baseline['common_terms']}")
            print(f"  - common_phrases: {text_baseline['common_phrases']}")
            print(
                "  - cleaning: "
                f"stop_words={text_diagnostics['stop_word_count']}, "
                f"min_favorite_docs={text_diagnostics['min_favorite_docs']}, "
                f"tokenizer={text_diagnostics['tokenizer_mode']}"
            )
            print("\nMost distinctive text features vs corpus (favorites - non-favorites)")
            for term, gain, fav_weight, non_weight in text_diagnostics["distinctive_features"][:15]:
                print(
                    f"  - {term}: delta={gain:.4f} "
                    f"(favorites={fav_weight:.4f}, corpus_non_favorites={non_weight:.4f})"
                )
            if norec:
                return 0

            structured_ranked = score_candidates(
                scoped_students, favorite_students, structured_baseline
            )
            text_ranked = score_candidates_text_only(
                scoped_students, favorite_students, text_baseline
            )
            ranked = combine_candidate_lists(structured_ranked, text_ranked)
        elif text_only:
            baseline, diagnostics = derive_text_baseline(
                favorite_students, scoped_students, use_spacy=use_spacy
            )

            print("\nText-only commonality baseline")
            print(f"  - common_terms: {baseline['common_terms']}")
            print(f"  - common_phrases: {baseline['common_phrases']}")
            print(
                "  - cleaning: "
                f"stop_words={diagnostics['stop_word_count']}, "
                f"min_favorite_docs={diagnostics['min_favorite_docs']}, "
                f"tokenizer={diagnostics['tokenizer_mode']}"
            )
            print("\nMost distinctive text features vs corpus (favorites - non-favorites)")
            for term, gain, fav_weight, non_weight in diagnostics["distinctive_features"][:15]:
                print(
                    f"  - {term}: delta={gain:.4f} "
                    f"(favorites={fav_weight:.4f}, corpus_non_favorites={non_weight:.4f})"
                )
            if norec:
                return 0

            ranked = score_candidates_text_only(scoped_students, favorite_students, baseline)
        else:
            baseline, diagnostics = derive_baseline(favorite_students)
            payload = build_search_filter_payload(baseline)

            print("\nDerived baseline")
            for key in [
                "country",
                "gender",
                "program_type",
                "gpa_floor",
                "age_floor",
                "single_placement",
                "double_placement",
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
            if norec:
                return 0

            ranked = score_candidates(scoped_students, favorite_students, baseline)

        print(f"\nTop {top_n} recommendation candidates")
        for idx, candidate in enumerate(ranked[:top_n], start=1):
            print(
                f"{idx}. app_id={candidate.app_id} | score={candidate.score} | "
                f"name={candidate.first_name} | country={candidate.country} | "
                f"program={candidate.program_type}"
            )
            print(f"   reasons: {', '.join(candidate.reasons)}")

        if not ranked:
            print("No recommendation candidates scored above zero with current heuristic.")

        return 0
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="POC: derive recommendation query inputs from a user's favorite students."
    )
    parser.add_argument(
        "--username",
        type=str,
        default=None,
        help="Optional username override. Defaults to Harrison/admin lookup.",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=10,
        help="How many recommendation candidates to print.",
    )
    parser.add_argument(
        "--text-only",
        action="store_true",
        default=False,
        help="Use free-text profile fields only to derive commonalities and recommendations.",
    )
    parser.add_argument(
        "--norec",
        action="store_true",
        default=False,
        help="Show only overlap/characteristics from favorites, skip recommendation candidates.",
    )
    parser.add_argument(
        "--combined",
        action="store_true",
        default=False,
        help="Run both structured and text analyses together and combine recommendation scores.",
    )
    parser.add_argument(
        "--compare",
        type=str,
        default="all",
        help="Status scope for corpus comparison/recommendations (e.g., all, allocated, unassigned).",
    )
    parser.add_argument(
        "--spacy",
        action="store_true",
        default=False,
        help="Use spaCy tokenization for text analysis instead of default tokenization.",
    )
    parser.add_argument(
        "--spacy-only",
        action="store_true",
        default=False,
        help="Run standalone spaCy analysis over favorites only and output commonalities.",
    )
    parser.add_argument(
        "--spacy-engine",
        action="store_true",
        default=False,
        help="Use standalone spaCy commonalities plus favorite interests to generate recommendations.",
    )
    parser.add_argument(
        "--last-n-placed",
        type=int,
        default=None,
        help="Use N most recently placed students from placement_metrics as baseline instead of favorites.",
    )

    args = parser.parse_args()
    return run(
        username=args.username,
        top_n=max(1, args.top_n),
        text_only=args.text_only,
        norec=args.norec,
        combined=args.combined,
        compare=args.compare,
        use_spacy=args.spacy,
        spacy_only=args.spacy_only,
        spacy_engine=args.spacy_engine,
        last_n_placed=args.last_n_placed,
    )


if __name__ == "__main__":
    raise SystemExit(main())
