from backend.agents.llm import allow_llm_fallback, call_groq_json
from backend.state import ProjectState
from backend.utils import complete_agent, load_prompt, set_agent_status, write_json

MAX_TOKENS = 1800


def run_analyst(state: ProjectState) -> ProjectState:
    set_agent_status(state, "analyst", "running")
    try:
        state["requirements"] = call_groq_json(
            agent_name="analyst",
            system_prompt=load_prompt("analyst_prompt.txt"),
            user_content=state["idea"],
            temperature=0.25,
            max_tokens=MAX_TOKENS,
        )
        state.setdefault("llm_calls", []).append({"agent": "analyst", "provider": "groq", "status": "success"})
        complete_agent(state, "analyst")
    except Exception as exc:
        if not allow_llm_fallback():
            set_agent_status(state, "analyst", "error")
            state["fatal_error"] = True
            raise
        state.setdefault("errors", []).append(f"Analyst used fallback after LLM error: {exc}")
        state["requirements"] = fallback_requirements(state.get("idea", ""))
        state.setdefault("llm_calls", []).append({"agent": "analyst", "provider": "groq", "status": "fallback"})
        complete_agent(state, "analyst")

    write_json(state["run_id"], "requirements.json", state["requirements"])
    return state


def fallback_requirements(idea: str) -> dict:
    business_type = infer_business_type(idea)
    return {
        "problem_statement": f"{business_type.title()} teams need a simple way to manage daily work, customer follow-ups, due dates, and revenue without spreadsheets or missed commitments.",
        "target_audience": f"Local {business_type} owners, staff, and solo operators who need a practical app in their own language.",
        "local_context": {
            "geography": "India-first local business context",
            "business_type": business_type,
            "operating_reality": "Small teams handle bookings, orders, customer calls, payments, and reminders manually on phones or notebooks.",
            "language_needs": "English plus Indian local-language support for staff comfort.",
            "device_constraints": "Must work on laptop and mobile-width browser screens with low setup complexity.",
        },
        "primary_personas": [
            {
                "name": "Owner",
                "role": "Business decision maker",
                "goals": ["Track all work in one place", "Avoid missed deadlines", "See revenue and workload"],
                "pains": ["Manual follow-ups", "No dashboard", "Lost customer details"],
                "permissions": ["create", "edit", "delete", "view metrics"],
            },
            {
                "name": "Staff",
                "role": "Daily operator",
                "goals": ["Update statuses", "Find customer records", "Know what is due today"],
                "pains": ["Unclear priorities", "Language friction", "Repeated phone checks"],
                "permissions": ["create", "edit", "view"],
            },
        ],
        "core_features": [
            "customer and work item management",
            "create, edit, delete, search, and filter records",
            "due date and priority tracking",
            "dashboard metrics for open, upcoming, completed, and revenue",
            "follow-up notes and contact details",
            "local JSON persistence for offline-friendly demo use",
            "English, Hindi, and Kannada language switcher",
            "realistic seed data and reset demo flow",
        ],
        "user_stories": [
            "As a local owner, I want to create work records so that no customer request is lost.",
            "As staff, I want to filter by status so that I know what needs action.",
            "As an owner, I want dashboard metrics so that I can see workload and revenue quickly.",
            "As staff, I want local-language labels so that the app is comfortable to use.",
            "As an owner, I want demo data so that I can understand the app immediately.",
            "As staff, I want validation so that incomplete records are not saved.",
        ],
        "workflow_map": [
            {
                "name": "Create work record",
                "trigger": "New customer request",
                "actor": "Owner or staff",
                "steps": ["Enter customer", "Add work title", "Set due date", "Choose status", "Save"],
                "expected_outcome": "Record appears in dashboard and list.",
            },
            {
                "name": "Daily follow-up",
                "trigger": "Start of day",
                "actor": "Staff",
                "steps": ["Open dashboard", "Filter open/upcoming records", "Call customer", "Update notes/status"],
                "expected_outcome": "Team knows what is done and what remains.",
            },
        ],
        "data_entities": [
            {
                "name": "work_item",
                "purpose": "Tracks each customer request/order/booking",
                "important_fields": ["customerName", "phone", "title", "status", "priority", "dueDate", "amount", "notes"],
                "relationships": ["belongs to customer/contact"],
            }
        ],
        "business_rules": [
            "customer name is required",
            "title is required",
            "due date is required",
            "status must be one of new, confirmed, in_progress, completed",
            "amount must be numeric",
        ],
        "automation_requirements": [
            {
                "name": "upcoming work visibility",
                "trigger": "dashboard load",
                "action": "calculate upcoming non-completed records",
                "fallback": "show all open records",
            }
        ],
        "localization_requirements": {
            "default_language": "English",
            "supported_languages": ["English", "Hindi", "Kannada"],
            "copy_style": "simple operational language",
            "local_terms": ["customer", "due date", "amount", "status"],
            "date_time_currency_format": "India date formatting and INR currency",
        },
        "mvp_scope": {
            "included": ["dashboard", "CRUD records", "filters", "local-language labels", "seed data", "local API"],
            "excluded": ["payments integration", "SMS gateway", "multi-user auth", "cloud deployment"],
        },
        "success_metrics": ["open work items", "upcoming due items", "completed items", "total revenue"],
        "seed_data": [
            "New customer request due next week",
            "Confirmed booking with reminder due tomorrow",
            "In-progress work item requiring follow-up",
            "Completed delivery awaiting feedback",
        ],
        "acceptance_criteria": [
            "User can create, edit, delete, search, and filter records.",
            "Dashboard metrics update from saved records.",
            "App supports English, Hindi, and Kannada UI labels.",
            "Generated project passes check, test, and build scripts.",
        ],
    }


def infer_business_type(idea: str) -> str:
    lowered = idea.lower()
    for keyword in ("bakery", "fitness", "photography", "clinic", "salon", "restaurant", "tuition", "coach"):
        if keyword in lowered:
            return keyword
    return "local business"
