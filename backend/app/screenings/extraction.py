"""Deterministic conversion of retrieved provider results into screening answers and advisory evaluation."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ScreeningAnswer, ScreeningSession
from app.screenings.schemas import (
    AdvisoryRecommendation,
    InformationSource,
    InterestLevel,
    ScreeningAnswerUpsert,
    ScreeningEvaluationInput,
    WorkArrangementCompatibility,
)
from app.screenings.service import ScreeningService
from app.screenings.types import ScreeningSessionStatus

_KEY_ALIASES: dict[str, tuple[str, ...]] = {
    "willing_to_continue": ("willing_to_continue", "consent", "willing_to_proceed"),
    "exploring_opportunities": ("exploring_opportunities", "interest", "interest_level", "exploring"),
    "total_experience_years": ("total_experience_years", "total_experience", "experience_years"),
    "relevant_experience_years": ("relevant_experience_years", "relevant_experience"),
    "skills_and_technologies": ("skills_and_technologies", "skills", "technologies", "tech_stack"),
    "current_compensation": ("current_compensation", "current_ctc", "current_salary"),
    "expected_compensation": ("expected_compensation", "expected_ctc", "expected_salary"),
    "notice_period": ("notice_period", "joining_time", "availability_to_join"),
    "location_and_work_arrangement": (
        "location_and_work_arrangement",
        "location",
        "work_arrangement",
        "work_arrangement_preference",
    ),
    "interview_availability": ("interview_availability", "availability", "interview_slots"),
}

_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
_NEGATIVE_WORDS = ("no", "not interested", "decline", "declined", "stop", "unsubscribe", "refuse")
_POSITIVE_WORDS = ("yes", "yeah", "sure", "interested", "exploring", "open", "actively")


def _extract_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        num = float(value)
        return num if 0 <= num <= 80 else None
    if isinstance(value, str):
        match = _NUMBER_RE.search(value)
        if match:
            num = float(match.group(0))
            return num if 0 <= num <= 80 else None
    return None


def _extract_skills(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()][:100]
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()][:100]
    return []


def _infer_source(
    explicit_source: Any,
    text_value: str,
    transcript: str | None,
) -> InformationSource:
    if explicit_source in {"explicit", "inferred"}:
        return explicit_source
    if transcript and text_value and text_value.strip().lower() in transcript.lower():
        return "explicit"
    return "inferred"


def _parse_interest_level(text_value: str | None) -> InterestLevel:
    if not text_value:
        return "not_asked"
    lowered = text_value.lower()
    if any(word in lowered for word in _NEGATIVE_WORDS):
        return "not_interested"
    if any(word in lowered for word in _POSITIVE_WORDS):
        return "interested"
    return "uncertain"


def _parse_work_compatibility(text_value: str | None) -> WorkArrangementCompatibility | None:
    if not text_value:
        return None
    lowered = text_value.lower()
    if "not compatible" in lowered or "incompatible" in lowered:
        return "not_compatible"
    if any(word in lowered for word in ("remote", "hybrid", "onsite", "on-site", "bengaluru", "bangalore", "relocat")):
        return "compatible"
    return "unclear"


class ScreeningResultProcessor:
    """Converts persisted provider transcript/summary/extracted_data into structured screening models."""

    def __init__(self, db: Session):
        self.db = db
        self.screening_service = ScreeningService(db)

    def process_provider_results(self, session_id: UUID) -> bool:
        """Process stored provider results for a screening session.

        Returns True if results were available and processed, False if no provider
        transcript, summary, or extracted data is present yet.
        """
        session = self.db.get(ScreeningSession, session_id)
        if session is None:
            return False

        has_provider_data = any(
            value is not None
            for value in (session.provider_transcript, session.provider_summary, session.provider_extracted_data)
        )
        if not has_provider_data:
            return False

        # Ensure session is in_progress if still created so answers can be persisted.
        if session.status == ScreeningSessionStatus.CREATED.value:
            self.screening_service.update_status(session_id, ScreeningSessionStatus.IN_PROGRESS)
            session = self.db.get(ScreeningSession, session_id)

        can_edit_answers = session.status in {
            ScreeningSessionStatus.CREATED.value,
            ScreeningSessionStatus.IN_PROGRESS.value,
        }
        extracted_dict = session.provider_extracted_data if isinstance(session.provider_extracted_data, dict) else {}

        if can_edit_answers and extracted_dict:
            self._persist_answers_from_extracted_data(session, extracted_dict)

        answers = list(
            self.db.scalars(
                select(ScreeningAnswer).where(ScreeningAnswer.session_id == session_id)
            ).all()
        )
        answer_map = {answer.question_key: answer for answer in answers}

        if can_edit_answers:
            next_status = self._determine_next_status(session, answer_map)
            self.screening_service.update_status(session_id, next_status)

        evaluation_input = self._build_evaluation_input(session, answer_map, extracted_dict)
        self.screening_service.save_evaluation(session_id, evaluation_input)
        return True

    def _persist_answers_from_extracted_data(
        self,
        session: ScreeningSession,
        extracted_dict: dict[str, Any],
    ) -> None:
        lowered_lookup = {str(k).strip().lower(): v for k, v in extracted_dict.items()}
        for question in session.question_config:
            q_key = question["question_key"]
            aliases = _KEY_ALIASES.get(q_key, (q_key,))
            raw_entry = None
            for alias in aliases:
                if alias in lowered_lookup:
                    raw_entry = lowered_lookup[alias]
                    break
            if raw_entry is None:
                continue

            if isinstance(raw_entry, dict):
                value = raw_entry.get("value", raw_entry.get("normalized_value"))
                orig = raw_entry.get("original_response")
                if orig is None and value is not None:
                    orig = ", ".join(str(v) for v in value) if isinstance(value, list) else str(value)
                source = _infer_source(raw_entry.get("source"), str(orig or ""), session.provider_transcript)
                confidence = raw_entry.get("confidence")
                is_missing = bool(raw_entry.get("is_missing")) or orig is None or not str(orig).strip()
            else:
                orig = ", ".join(str(v) for v in raw_entry) if isinstance(raw_entry, list) else str(raw_entry)
                value = raw_entry
                source = _infer_source(None, orig, session.provider_transcript)
                confidence = None
                is_missing = not orig.strip()

            if is_missing:
                payload = ScreeningAnswerUpsert(is_missing=True)
            else:
                payload = ScreeningAnswerUpsert(
                    original_response=str(orig).strip(),
                    normalized_value=value,
                    information_source=source,
                    confidence=float(confidence) if isinstance(confidence, (int, float)) else None,
                    is_missing=False,
                )
            self.screening_service.save_answer(session.id, q_key, payload)

    def _determine_next_status(
        self,
        session: ScreeningSession,
        answer_map: dict[str, ScreeningAnswer],
    ) -> ScreeningSessionStatus:
        consent = answer_map.get("willing_to_continue")
        if consent is not None and not consent.is_missing and consent.original_response:
            if any(word in consent.original_response.lower() for word in _NEGATIVE_WORDS):
                return ScreeningSessionStatus.DECLINED

        required_keys = {item["question_key"] for item in session.question_config if item["required"]}
        answered_keys = {key for key, ans in answer_map.items() if not ans.is_missing}
        if required_keys <= answered_keys:
            return ScreeningSessionStatus.COMPLETED
        return ScreeningSessionStatus.INCOMPLETE

    def _build_evaluation_input(
        self,
        session: ScreeningSession,
        answer_map: dict[str, ScreeningAnswer],
        extracted_dict: dict[str, Any],
    ) -> ScreeningEvaluationInput:
        field_sources: dict[str, InformationSource] = {}

        def answer_text(key: str) -> tuple[str | None, InformationSource | None]:
            ans = answer_map.get(key)
            if ans is None or ans.is_missing or not ans.original_response:
                return None, None
            src: InformationSource = "explicit" if ans.information_source == "explicit" else "inferred"
            return ans.original_response, src

        total_raw, total_src = answer_text("total_experience_years")
        total_exp = _extract_float(
            answer_map["total_experience_years"].normalized_value
            if "total_experience_years" in answer_map and not answer_map["total_experience_years"].is_missing
            else total_raw
        )
        if total_exp is not None and total_src:
            field_sources["total_experience_years"] = total_src

        rel_raw, rel_src = answer_text("relevant_experience_years")
        rel_exp = _extract_float(
            answer_map["relevant_experience_years"].normalized_value
            if "relevant_experience_years" in answer_map and not answer_map["relevant_experience_years"].is_missing
            else rel_raw
        )
        if rel_exp is not None and total_exp is not None and rel_exp > total_exp:
            rel_exp = total_exp
        if rel_exp is not None and rel_src:
            field_sources["relevant_experience_years"] = rel_src

        skills_raw, skills_src = answer_text("skills_and_technologies")
        skills_val = (
            answer_map["skills_and_technologies"].normalized_value
            if "skills_and_technologies" in answer_map and not answer_map["skills_and_technologies"].is_missing
            else skills_raw
        )
        skills = _extract_skills(skills_val)
        if skills and skills_src:
            field_sources["skills"] = skills_src

        curr_comp, curr_src = answer_text("current_compensation")
        if curr_comp and curr_src:
            field_sources["current_compensation"] = curr_src

        exp_comp, exp_src = answer_text("expected_compensation")
        if exp_comp and exp_src:
            field_sources["expected_compensation"] = exp_src

        notice, notice_src = answer_text("notice_period")
        if notice and notice_src:
            field_sources["notice_period"] = notice_src

        loc_pref, loc_src = answer_text("location_and_work_arrangement")
        work_compat = _parse_work_compatibility(loc_pref)
        if loc_pref and loc_src:
            field_sources["location"] = loc_src
            field_sources["work_arrangement_preference"] = loc_src
            if work_compat is not None:
                field_sources["work_arrangement_compatibility"] = "inferred"

        interest_raw, interest_src = answer_text("exploring_opportunities")
        interest_level = _parse_interest_level(interest_raw)
        if interest_level != "not_asked" and interest_src:
            field_sources["interest_level"] = "inferred" if interest_src == "inferred" else "explicit"

        avail, avail_src = answer_text("interview_availability")
        if avail and avail_src:
            field_sources["interview_availability"] = avail_src

        missing_information: list[str] = []
        for question in session.question_config:
            q_key = question["question_key"]
            ans = answer_map.get(q_key)
            if ans is None or ans.is_missing:
                label = q_key.replace("_", " ")
                missing_information.append(f"{label} (required)" if question["required"] else label)

        required_missing = [
            item["question_key"]
            for item in session.question_config
            if item["required"] and (item["question_key"] not in answer_map or answer_map[item["question_key"]].is_missing)
        ]

        if session.status == ScreeningSessionStatus.DECLINED.value or interest_level == "not_interested":
            recommendation: AdvisoryRecommendation = "no_recommendation"
            reason = "Candidate declined to proceed or indicated they are not currently interested."
            next_action = "Close screening or confirm candidate preference manually before any follow-up."
        elif not required_missing and answer_map:
            recommendation = "proceed_to_human_review"
            reason = "All required screening questions have recorded responses from the completed call."
            next_action = "Recruiter to review transcript, verify compensation/notice details, and decide on interview."
        elif answer_map or extracted_dict:
            recommendation = "request_more_information"
            reason = f"Completed call left {len(required_missing)} required screening item(s) unanswered."
            next_action = "Review transcript and follow up with candidate on missing required details."
        else:
            recommendation = "request_more_information"
            reason = "Call transcript/summary was retrieved, but structured answers have not been extracted yet."
            next_action = "Review the raw transcript and record screening answers manually."

        summary = (session.provider_summary or "").strip()
        if not summary:
            answered_count = sum(1 for ans in answer_map.values() if not ans.is_missing)
            summary = (
                f"Call completed with {answered_count} recorded answer(s) and "
                f"{len(required_missing)} missing required item(s). "
                "Advisory summary generated from retrieved provider data."
            )

        return ScreeningEvaluationInput(
            total_experience_years=total_exp,
            relevant_experience_years=rel_exp,
            skills=skills,
            current_compensation=curr_comp,
            expected_compensation=exp_comp,
            notice_period=notice,
            location=loc_pref,
            work_arrangement_preference=loc_pref,
            work_arrangement_compatibility=work_compat,
            interest_level=interest_level,
            interview_availability=avail,
            field_sources=field_sources,
            missing_information=missing_information,
            screening_summary=summary,
            advisory_recommendation=recommendation,
            recommendation_reason=f"{reason} (Advisory only; recruiter makes the final decision.)",
            suggested_next_action=next_action,
        )
