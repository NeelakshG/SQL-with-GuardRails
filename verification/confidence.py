SHAPE_WEIGHT = 0.5
JUDGE_WEIGHT = 0.15
CRITIC_WEIGHT = 0.35

# Product decision, not a math one -- lower = more wrong answers slip through, higher = more correct ones get needlessly flagged.
NEEDS_REVIEW_THRESHOLD = 0.6


def combine(shape_ok, judge_score, critic_has_issue, critic_confidence):
    shape_score = 1.0 if shape_ok else 0.0

    if judge_score is None:
        judge_score = 0.5

    if critic_has_issue is True:
        critic_score = 0.0
    elif critic_confidence is not None:
        critic_score = critic_confidence
    else:
        critic_score = 0.5

    confidence = (
        SHAPE_WEIGHT * shape_score
        + JUDGE_WEIGHT * judge_score
        + CRITIC_WEIGHT * critic_score
    )

    return {
        "confidence": round(confidence, 3),
        "needs_review": confidence < NEEDS_REVIEW_THRESHOLD,
        "breakdown": {
            "shape_score": shape_score,
            "judge_score": judge_score,
            "critic_score": critic_score,
        },
    }
