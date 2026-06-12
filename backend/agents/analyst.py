from backend.agents.llm import allow_fallback_for_idea, call_groq_json
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
        if not allow_fallback_for_idea(state.get("idea", "")):
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
    if business_type == "bakery":
        return bakery_fallback_requirements(idea)
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


def bakery_fallback_requirements(idea: str) -> dict:
    return {
        "problem_statement": "Bakery teams need one place to manage custom cake orders, bread and pastry batches, pickup timing, payment status, customer follow-ups, and daily production without spreadsheet confusion.",
        "target_audience": "Local bakery owners, counter staff, bakers, and delivery staff who manage customer orders, production queues, and pickup commitments.",
        "local_context": {
            "geography": "India-first local bakery context",
            "business_type": "bakery",
            "operating_reality": "Small bakery teams take orders through walk-ins, WhatsApp, phone calls, and Instagram while coordinating kitchen production and pickups.",
            "language_needs": "English plus Hindi and Kannada labels for staff comfort.",
            "device_constraints": "Must work on laptop and mobile-width browser screens with low setup complexity.",
        },
        "primary_personas": [
            {
                "name": "Bakery Owner",
                "role": "Business decision maker",
                "goals": ["Track orders and revenue", "Avoid missed pickups", "Prioritize production"],
                "pains": ["Lost WhatsApp orders", "Unclear payment status", "No daily production view"],
                "permissions": ["create", "edit", "delete", "view metrics"],
            },
            {
                "name": "Counter Staff",
                "role": "Order taker",
                "goals": ["Enter customer details quickly", "Update payment and pickup status", "Find orders fast"],
                "pains": ["Repeated customer calls", "Manual notes", "Language friction"],
                "permissions": ["create", "edit", "view"],
            },
        ],
        "core_features": [
            "custom cake order management",
            "bread and pastry order tracking",
            "daily bakery production queue",
            "pickup date and pickup time scheduling",
            "customer phone, notes, and follow-up history",
            "payment status and bakery revenue dashboard",
            "search and filters by status, priority, payment, and due date",
            "English, Hindi, and Kannada language switcher",
            "realistic bakery seed data and reset demo flow",
        ],
        "user_stories": [
            "As a bakery owner, I want to see all cake and bread orders due today so that production is prioritized.",
            "As counter staff, I want to create a custom cake order with pickup time so that no customer request is missed.",
            "As a bakery owner, I want payment status metrics so that pending collections are visible.",
            "As staff, I want local-language labels so that daily use is comfortable.",
        ],
        "workflow_map": [
            {
                "name": "Create bakery order",
                "trigger": "Customer places a cake, bread, pastry, or catering order",
                "actor": "Counter staff",
                "steps": ["Enter customer", "Select bakery item", "Add quantity and notes", "Set pickup date/time", "Save order"],
                "expected_outcome": "Order appears in production queue and dashboard metrics.",
            },
            {
                "name": "Daily production planning",
                "trigger": "Start of bakery day",
                "actor": "Bakery owner",
                "steps": ["Open dashboard", "Review pending pickups", "Assign staff", "Update production status"],
                "expected_outcome": "Team knows which cakes, breads, and pastries are due next.",
            },
        ],
        "data_entities": [
            {
                "name": "bakery_order",
                "purpose": "Tracks each custom cake, bread, pastry, or catering order",
                "important_fields": ["customerName", "phone", "itemType", "quantity", "status", "priority", "pickupDate", "pickupTime", "amount", "paymentStatus", "notes"],
                "relationships": ["belongs to customer/contact"],
            }
        ],
        "business_rules": [
            "customer name is required",
            "bakery item or order title is required",
            "pickup date is required",
            "status must be one of new, confirmed, in_progress, completed",
            "amount must be numeric",
            "payment status must be pending, partial, or paid",
        ],
        "automation_requirements": [
            {
                "name": "production queue visibility",
                "trigger": "dashboard load",
                "action": "calculate upcoming non-completed bakery orders by pickup date",
                "fallback": "show all open bakery orders",
            }
        ],
        "localization_requirements": {
            "default_language": "English",
            "supported_languages": ["English", "Hindi", "Kannada"],
            "copy_style": "simple bakery operations language",
            "local_terms": ["order", "pickup", "amount", "payment", "production queue"],
            "date_time_currency_format": "India date formatting and INR currency",
        },
        "mvp_scope": {
            "included": ["dashboard", "CRUD bakery orders", "filters", "production queue", "local-language labels", "seed data", "local API"],
            "excluded": ["payment gateway", "SMS gateway", "multi-user auth", "cloud deployment"],
        },
        "success_metrics": ["open bakery orders", "today's pickups", "completed orders", "pending payments", "total revenue"],
        "seed_data": [
            "Custom birthday cake order for pickup tomorrow",
            "Bread subscription batch due this evening",
            "Pastry box catering order with partial payment",
            "Completed cupcake order awaiting customer feedback",
        ],
        "acceptance_criteria": [
            "User can create, edit, delete, search, and filter bakery orders.",
            "Dashboard metrics update from saved bakery records.",
            "Production queue shows upcoming pickups and assigned staff.",
            "App supports English, Hindi, and Kannada UI labels.",
            "Generated project passes check, test, and build scripts.",
        ],
    }


def infer_business_type(idea: str) -> str:
    lowered = idea.lower()
    keyword_profiles = [
        (("bakery", "cake", "baker"), "bakery"),
        (("salon", "saloon", "beauty", "spa", "hair", "makeup", "barber"), "salon"),
        (("clinic", "doctor", "patient", "dental", "health"), "clinic"),
        (("fitness", "fitness center", "fitness centre", "gym", "workout", "trainer", "yoga", "zumba"), "gym / fitness center"),
        (("restaurant", "cafe", "food", "dining", "table", "menu", "kitchen", "takeaway"), "restaurant"),
        (("coaching center", "coaching centre", "coaching", "tuition", "school", "student", "academy"), "coaching center"),
        (("photography", "photo", "shoot"), "photography"),
    ]
    for keywords, business_type in keyword_profiles:
        if any(keyword in lowered for keyword in keywords):
            return business_type
    return "local business"
