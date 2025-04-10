from langchain.chat_models import ChatGoogleGenerativeAI
from langchain.tools import tool
from langchain_core.runnables import RunnableLambda
from langgraph.graph import StateGraph, END
from langchain.memory import ConversationBufferMemory
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from datetime import datetime, timedelta
from twilio.rest import Client
import os, json, time, webbrowser

# === CONFIG === #
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TWILIO_SID = os.getenv("TWILIO_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
FROM_WHATSAPP = "whatsapp:+14155238886"

# === IN-MEMORY STORE === #
user_store = {
    "whatsapp_number": None,
    "meeting_links": []
}

# === MEMORY === #
memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)

# === LLM SETUP === #
llm = ChatGoogleGenerativeAI(model="gemini-pro", google_api_key=GEMINI_API_KEY)

# === TOOLS === #
@tool
def add_event_to_calendar(title: str, date: str, time: str, location: str = "") -> str:
    """Adds an event to Google Calendar."""
    creds = Credentials.from_authorized_user_file("token.json", ["https://www.googleapis.com/auth/calendar"])
    service = build('calendar', 'v3', credentials=creds)

    start = f"{date}T{time}:00"
    end = (datetime.strptime(time, "%H:%M") + timedelta(hours=1)).strftime("%H:%M")
    end = f"{date}T{end}:00"

    event = {
        'summary': title,
        'start': {'dateTime': start, 'timeZone': 'America/New_York'},
        'end': {'dateTime': end, 'timeZone': 'America/New_York'},
        'location': location
    }

    created = service.events().insert(calendarId='primary', body=event).execute()

    # If it's a meeting and the location looks like a link, store it
    if "meeting" in title.lower() and location.startswith("http"):
        user_store["meeting_links"].append({"link": location, "datetime": start})

    return f"📅 Event created: {created.get('htmlLink')}"


@tool
def send_whatsapp_message(message: str) -> str:
    """Sends a WhatsApp message to the stored user."""
    to_number = user_store.get("whatsapp_number")
    if not to_number:
        return "❌ No WhatsApp number stored. Please provide it first."

    client = Client(TWILIO_SID, TWILIO_AUTH_TOKEN)
    client.messages.create(
        body=message,
        from_=FROM_WHATSAPP,
        to=to_number
    )
    return "📲 WhatsApp message sent!"


@tool
def get_new_events(event_type: str) -> str:
    """Polls an event API and returns new event data as text."""
    return f"Found event: {event_type.title()} Hike at 2025-04-12 10:00 at Central Park."


@tool
def store_whatsapp_number(number: str) -> str:
    """Stores the user's WhatsApp number for future use."""
    if not number.startswith("whatsapp:"):
        number = f"whatsapp:{number}"
    user_store["whatsapp_number"] = number
    return f"✅ Stored WhatsApp number: {number}"


@tool
def join_scheduled_meetings(_: dict = {}) -> str:
    """Checks and joins any scheduled meeting if its time has come."""
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:00")
    for meeting in user_store["meeting_links"]:
        if meeting["datetime"] <= now:
            webbrowser.open(meeting["link"])
            return f"🧑‍💻 Joining meeting now: {meeting['link']}"
    return "⏱️ No meetings to join at this time."


# === LANGGRAPH FLOW === #
def parse_user_input(state):
    user_input = state["input"]
    if user_input.strip().lower().startswith("my whatsapp is"):
        number = user_input.split()[-1]
        return {"stored_number": store_whatsapp_number.invoke({"number": number})}

    response = llm.invoke(
        f"Extract event type, title, date (YYYY-MM-DD), time (HH:MM), and location from: '{user_input}'\nRespond as JSON."
    )
    try:
        event_data = json.loads(response.content.strip())
        return {"event_data": event_data}
    except Exception as e:
        return {"error": str(e)}


def poll_events(state):
    event_type = state["event_data"].get("event_type", "hiking")
    event_description = get_new_events.invoke({"event_type": event_type})
    return {"event_description": event_description}


def add_to_calendar(state):
    data = state["event_data"]
    result = add_event_to_calendar.invoke(data)
    return {"calendar_link": result}


def send_notification(state):
    link = state.get("calendar_link", "")
    message = f"🚨 New event scheduled and added to your calendar!\n{link}"
    result = send_whatsapp_message.invoke({"message": message})
    return {"notification_status": result}


def build_graph():
    workflow = StateGraph()
    workflow.add_node("parse", RunnableLambda(parse_user_input))
    workflow.add_node("poll", RunnableLambda(poll_events))
    workflow.add_node("calendar", RunnableLambda(add_to_calendar))
    workflow.add_node("notify", RunnableLambda(send_notification))

    workflow.set_entry_point("parse")
    workflow.add_conditional_edges("parse", lambda state: "notify" if "stored_number" in state else "poll")
    workflow.add_edge("poll", "calendar")
    workflow.add_edge("calendar", "notify")
    workflow.add_edge("notify", END)

    return workflow.compile()


workflow = build_graph()


def run_event_bot(user_input):
    initial_state = {"input": user_input}
    result = workflow.invoke(initial_state)
    return result


if __name__ == "__main__":
    print("🤖 LangGraph Event Manager Ready. Type your request!")
    while True:
        try:
            user_input = input("You: ")
            if user_input.lower() in ["exit", "quit"]:
                break
            output = run_event_bot(user_input)
            print("Bot:", output.get("notification_status") or output.get("stored_number") or "Done.")

            # Attempt to join a meeting if one is scheduled
            join_result = join_scheduled_meetings()
            if "Joining" in join_result:
                print("Bot:", join_result)
        except KeyboardInterrupt:
            break

