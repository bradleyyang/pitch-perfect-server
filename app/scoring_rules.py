from typing import Dict, List, Tuple

AGENT_WEIGHTS = {
    "deck": 0.15,
    "text": 0.2,
    "speech_content": 0.15,
    "audio": 0.2,
    "voice": 0.15,
    "transcription": 0.15,
}


def apply_scoring_rules(
    combine_summary: Dict[str, int],
    agent_scores: Dict[str, int],
    warnings: List[str],
    adjustments: List[Dict[str, int]],
) -> None:
    """Adjust combine summary based on per-agent scores and record warnings."""
    if not agent_scores:
        return

    total_weight = sum(AGENT_WEIGHTS.values())
    weighted_sum = 0.0
    gathered = 0.0
    for agent, weight in AGENT_WEIGHTS.items():
        score = agent_scores.get(agent)
        if score is None:
            continue
        weighted_sum += score * weight
        gathered += weight

    if gathered == 0:
        return

    weighted_average = weighted_sum / gathered
    current_score = combine_summary.get("overallScore", 65)

    if weighted_average + 5 < current_score:
        target = max(1, int(round(weighted_average)))
        penalty = current_score - target
        combine_summary["overallScore"] = target
        adjustments.append(
            {
                "type": "weighted_average",
                "original": current_score,
                "adjusted": target,
                "penalty": penalty,
            }
        )
        warnings.append(
            f"Summary lowered by {penalty} pts to match the weighted average of agent scores ({weighted_average:.1f})."
        )

    max_agent = max(agent_scores.values())
    min_agent = min(agent_scores.values())
    if (max_agent - min_agent) > 20:
        warnings.append(
            f"Agent scores vary by {max_agent - min_agent} pts; the combine summary should favor the weakest modality."
        )

    for agent, score in agent_scores.items():
        if abs(score - current_score) > 15:
            warnings.append(
                f"{agent.title()} agent score ({score}) differs from the combine summary ({current_score}) by over 15 pts."
            )
