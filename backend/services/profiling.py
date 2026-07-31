import random
from typing import List

PROFILING_QUESTIONS: List[str] = [
    "What is the vibe today? (e.g., cozy, intense, mind-bending, feel-good)",
    "What's your pacing preference — slow burn or fast-paced action?",
    "Classic or modern? Any era you are drawn to?",
    "Who are you watching with, and how much time do you have?",
    "Any genres, actors, or tropes you want — or definitely want to avoid?",
]


def pick_target_question_count() -> int:
    return random.randint(3, 5)


def build_question_sequence(target_count: int) -> List[str]:
    pool = PROFILING_QUESTIONS.copy()
    random.shuffle(pool)
    return pool[:target_count]
