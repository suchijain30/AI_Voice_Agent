from app.screenings.schemas import ScreeningQuestion


# Initial reusable defaults derived from the POC screening topics. Each session
# stores a snapshot so later configuration edits do not alter historical sessions.
INITIAL_SCREENING_QUESTIONS = [
    ScreeningQuestion(
        question_key="willing_to_continue",
        question_text="Are you willing to continue with a short screening conversation?",
        required=True,
        order=0,
        category="consent",
        follow_up_guidance="If the candidate declines, thank them and end the screening politely.",
    ),
    ScreeningQuestion(
        question_key="exploring_opportunities",
        question_text="Are you currently exploring new job opportunities?",
        required=True,
        order=1,
        category="interest",
        follow_up_guidance="If unclear, ask whether they would consider discussing this role.",
    ),
    ScreeningQuestion(
        question_key="total_experience_years",
        question_text="How many years of total professional work experience do you have?",
        required=True,
        order=2,
        category="experience",
        follow_up_guidance="Clarify approximate duration if the answer is vague; do not infer without marking it.",
    ),
    ScreeningQuestion(
        question_key="relevant_experience_years",
        question_text="How much of that experience is relevant to this role?",
        required=True,
        order=3,
        category="experience",
        follow_up_guidance="Ask which prior responsibilities or projects are most relevant.",
    ),
    ScreeningQuestion(
        question_key="skills_and_technologies",
        question_text="Which skills or technologies have you used that are relevant to this role?",
        required=True,
        order=4,
        category="skills",
        follow_up_guidance="Ask for a brief example if the response is only a list and more context is needed.",
    ),
    ScreeningQuestion(
        question_key="current_compensation",
        question_text="If you are comfortable sharing, what is your current compensation?",
        required=False,
        order=5,
        category="compensation",
        follow_up_guidance="Respect a refusal; record the answer as missing rather than estimating.",
    ),
    ScreeningQuestion(
        question_key="expected_compensation",
        question_text="What compensation range are you expecting for your next role?",
        required=True,
        order=6,
        category="compensation",
        follow_up_guidance="Clarify currency and whether the amount is annual if needed.",
    ),
    ScreeningQuestion(
        question_key="notice_period",
        question_text="What is your notice period, and when could you potentially join?",
        required=True,
        order=7,
        category="availability",
        follow_up_guidance="Clarify the duration and whether it is negotiable, if the candidate is willing to answer.",
    ),
    ScreeningQuestion(
        question_key="location_and_work_arrangement",
        question_text="Where are you currently located, and what work arrangement do you prefer?",
        required=True,
        order=8,
        category="location",
        follow_up_guidance="Clarify relocation or onsite/hybrid/remote preference only as relevant to the role.",
    ),
    ScreeningQuestion(
        question_key="interview_availability",
        question_text="When would you be available for a follow-up interview?",
        required=True,
        order=9,
        category="availability",
        follow_up_guidance="Capture the candidate's stated availability; do not schedule an interview in this phase.",
    ),
]
