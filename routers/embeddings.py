# from routers.student import STUDENTS
# from typing import List
# from sentence_transformers import SentenceTransformer
# from models.student import FullStudent  # adjust import as needed
# from torch import Tensor
# from sentence_transformers import util

# from fastapi import Query, APIRouter

# router = APIRouter(prefix="/embedding", tags=["embedding"])

# model = SentenceTransformer("all-MiniLM-L6-v2")  # fast + lightweight

# def student_to_embedding_text(student: FullStudent) -> str:
#     """Convert a FullStudent instance into a human-readable text block for embedding."""
#     parts: List[str] = []

#     if student.gender_desc:
#         parts.append(f"Gender: {student.gender_desc}")
#     if student.selected_interests:
#         parts.append(f"Interests: {', '.join(student.selected_interests)}")
#     if student.family_description:
#         parts.append(f"Family Description: {student.family_description}")
#     if student.favorite_subjects:
#         parts.append(f"Favorite Subjects: {student.favorite_subjects}")
#     if student.photo_comments:
#         parts.append(f"Photo Comments: {student.photo_comments}")
#     if student.religion:
#         parts.append(f"Religion: {student.religion}")
#     if student.allergy_comments:
#         parts.append(f"Allergy Comments: {student.allergy_comments}")
#     if student.dietary_restrictions:
#         parts.append(f"Dietary Restrictions: {student.dietary_restrictions}")
#     if student.intro_message:
#         parts.append(f"Introduction: {student.intro_message}")
#     if student.message_to_host_family:
#         parts.append(f"Message to Host Family: {student.message_to_host_family}")
#     if student.message_from_natural_family:
#         parts.append(f"Message from Natural Family: {student.message_from_natural_family}")
#     if student.health_comments:
#         parts.append(f"Health Comments: {', '.join(student.health_comments)}")

#     return "\n".join(parts)


# def generate_student_embeddings(students: list[FullStudent]) -> dict[int, Tensor]:
#     """Generate and store embeddings keyed by student ID."""
#     texts = [student_to_embedding_text(s) for s in students]
#     embeddings = model.encode(texts, convert_to_tensor=True, normalize_embeddings=True)
#     return {s.id: emb for s, emb in zip(students, embeddings)}


# texts = [student_to_embedding_text(s) for s in STUDENTS]
# embeddings = model.encode(texts, convert_to_tensor=True, normalize_embeddings=True)

# @router.get("/search")
# def search_students(query: str = Query(...)):
#     query_emb = model.encode(query, convert_to_tensor=True, normalize_embeddings=True)
#     scores = util.cos_sim(query_emb, embeddings)[0]
    
#     # 🔹 Get top 15 highest similarity scores
#     top_k = min(15, len(STUDENTS))
#     top_indices = scores.topk(k=top_k).indices.tolist()
#     top_scores = scores[top_indices].tolist()

#     # Return matching STUDENTS + their scores
#     results = [
#         {"student": STUDENTS[i], "score": float(top_scores[idx])}
#         for idx, i in enumerate(top_indices)
#     ]

#     return {"query": query, "results": results}