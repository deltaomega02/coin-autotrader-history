"""ATHENA Lessons 관리.

OMNI lessons.md 패턴 부활.
주 1회 회고로 새 교훈 추출 → lessons.md 업데이트.
다음 결정 시 컨텍스트로 제공.
"""

from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from config import get_logger

logger = get_logger("lessons")

LESSONS_FILE = Path(__file__).parent.parent / "lessons" / "lessons.md"


def read_lessons() -> str:
    """현재 lessons.md 내용. AI 컨텍스트로 사용."""
    if not LESSONS_FILE.exists():
        return ""
    try:
        return LESSONS_FILE.read_text(encoding="utf-8")
    except Exception as e:
        logger.error(f"lessons.md 읽기 실패: {e}")
        return ""


def append_weekly_reflection(reflection: dict) -> bool:
    """주간 회고 결과를 lessons.md에 추가.

    Args:
        reflection: AI Reflection Agent 출력 (JSON)
    """
    if not reflection:
        return False

    try:
        LESSONS_FILE.parent.mkdir(parents=True, exist_ok=True)

        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        section = [
            f"\n\n## 주간 회고 — {date_str}",
            "",
            f"**Summary**: {reflection.get('weekly_summary', '')}",
            "",
        ]

        best = reflection.get("best_decision", {})
        if best:
            section.append(f"**최고 결정** ({best.get('date', '')}): {best.get('what', '')} — {best.get('why_good', '')}")

        worst = reflection.get("worst_decision", {})
        if worst:
            section.append(f"**최악 결정** ({worst.get('date', '')}): {worst.get('what', '')} — {worst.get('why_bad', '')}")

        patterns = reflection.get("patterns_found", [])
        if patterns:
            section.append("\n**발견된 패턴**:")
            for p in patterns:
                section.append(f"- {p}")

        new_lessons = reflection.get("new_lessons", [])
        if new_lessons:
            section.append("\n**새 교훈**:")
            for l in new_lessons:
                rule = l.get("rule", "")
                evidence = l.get("evidence", "")
                conf = l.get("confidence", "TENTATIVE")
                section.append(f"- [{conf}] {rule} (근거: {evidence})")

        revisions = reflection.get("lessons_to_revise", [])
        if revisions:
            section.append("\n**수정 필요**:")
            for r in revisions:
                section.append(f"- {r}")

        # 기존 파일에 append
        existing = read_lessons() or "# ATHENA Lessons\n\n자동 갱신 (주 1회). AI Manager가 매 결정 시 참조.\n"
        new_content = existing + "\n".join(section) + "\n"

        LESSONS_FILE.write_text(new_content, encoding="utf-8")
        logger.info(f"lessons.md 업데이트 완료 — 새 교훈 {len(new_lessons)}개")
        return True

    except Exception as e:
        logger.error(f"lessons.md 업데이트 실패: {e}")
        return False
