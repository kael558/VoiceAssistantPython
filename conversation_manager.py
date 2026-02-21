import hashlib
import json
import os
from datetime import datetime, timezone

from loguru import logger

BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "conversations")
os.makedirs(BASE_DIR, exist_ok=True)

MAX_MESSAGES = 20
COMPRESS_OLDEST = 10
KEEP_NEWEST = 10

IGNORED_MESSAGES = {"wifi"}


def _phone_to_filename(phone: str) -> str:
    safe = hashlib.sha256(phone.encode()).hexdigest()[:16]
    return os.path.join(BASE_DIR, f"{safe}.json")


def load_conversation(phone: str) -> dict:
    path = _phone_to_filename(phone)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"phone": phone, "memory": "", "messages": []}


def save_conversation(phone: str, data: dict) -> None:
    path = _phone_to_filename(phone)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Failed to save conversation for {phone}: {e}")


def add_message(phone: str, role: str, content: str) -> None:
    if content.strip().lower() in IGNORED_MESSAGES:
        return

    data = load_conversation(phone)
    data["messages"].append({
        "role": role,
        "content": content,
        "ts": datetime.now(timezone.utc).isoformat(),
    })
    save_conversation(phone, data)


def build_llm_context(phone: str, system_prompt: str) -> list[dict]:
    """Build the message list for the LLM, incorporating memory and recent messages."""
    data = load_conversation(phone)

    messages = [{"role": "system", "content": system_prompt}]

    if data.get("memory"):
        messages.append({
            "role": "system",
            "content": (
                "Below is a summary of earlier conversations with this user. "
                "Use it for context but do not repeat it back.\n\n"
                f"{data['memory']}"
            ),
        })

    for msg in data["messages"][-MAX_MESSAGES:]:
        messages.append({"role": msg["role"], "content": msg["content"]})

    return messages


def maybe_compress(phone: str, llm_client) -> None:
    """If the conversation exceeds MAX_MESSAGES, summarize the oldest COMPRESS_OLDEST
    messages into the memory block and keep only the newest KEEP_NEWEST."""
    data = load_conversation(phone)

    if len(data["messages"]) <= MAX_MESSAGES:
        return

    oldest = data["messages"][:COMPRESS_OLDEST]
    newest = data["messages"][COMPRESS_OLDEST:]

    conversation_text = "\n".join(
        f"{m['role'].upper()}: {m['content']}" for m in oldest
    )

    existing_memory = data.get("memory", "")
    prompt = (
        "You are a memory summarizer. Condense the following conversation excerpt "
        "into a concise factual summary (3-5 sentences). Preserve important facts, "
        "user preferences, names, locations, and any commitments or plans mentioned. "
        "Do NOT invent information.\n\n"
    )
    if existing_memory:
        prompt += f"Previous memory block:\n{existing_memory}\n\n"
    prompt += f"New conversation to summarize:\n{conversation_text}"

    try:
        response = llm_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": "Summarize this into a memory block."},
            ],
        )
        new_memory = response.choices[0].message.content
    except Exception as e:
        logger.error(f"Memory compression failed for {phone}: {e}")
        new_memory = existing_memory + "\n[Compression failed, messages dropped]"

    data["memory"] = new_memory
    data["messages"] = newest
    save_conversation(phone, data)
    logger.info(f"Compressed conversation for {phone}: {len(oldest)} msgs -> memory block")
