
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from pymongo import MongoClient, ASCENDING, DESCENDING
from mongo_config import MONGODB_URI, MONGODB_DB, COLL_MESSAGES
import backend  # for lo_save_file and graph lookups

# ---- Mongo client / indices ----
_client = MongoClient(MONGODB_URI)
_db = _client[MONGODB_DB]
_messages = _db[COLL_MESSAGES]

# Ensure indexes (safe to call many times)
_messages.create_index([("sender_id", ASCENDING), ("receiver_id", ASCENDING), ("created_at", DESCENDING)])
_messages.create_index([("participants", ASCENDING), ("created_at", DESCENDING)])

def _now_iso():
    return datetime.utcnow()

def _normalize_identity(name: str, *, role: str) -> Dict[str, str]:
    """
    name: current login username
    role: "super" (admin) or "normal" (user)
    Returns:
      {
        "user_type": "doctor" | "patient" | "admin_only",
        "person_id": <doctor_ID or patient_ID if mapped, else name>,
        "login_name": name,
        "role": role
      }
    """
    from login_backend import get_account_person_id, is_doctor_person, is_patient_person
    person_id = get_account_person_id(name) or name
    ut = "admin_only"
    if role == "super" and is_doctor_person(person_id):
        ut = "doctor"
    elif role == "normal" and is_patient_person(person_id):
        ut = "patient"
    return {"user_type": ut, "person_id": person_id, "login_name": name, "role": role}

def list_recipients_for_user(login_name: str, *, role: str) -> List[Dict[str, str]]:
    """
    Returns a list of dicts: { 'id': person_id, 'name': readable_name }
    Doctors -> their patients
    Patients -> their doctors
    """
    me = _normalize_identity(login_name, role=role)
    if me["user_type"] == "doctor":
        # doctor -> list patients (patient_ID, name)
        return [{"id": pid, "name": pname} for pid, pname in backend.get_patients_for_doctor(me["person_id"])]
    elif me["user_type"] == "patient":
        # patient -> list doctors (doctor_ID, name)
        return [{"id": did, "name": dname} for did, dname in backend.get_doctors_for_patient(me["person_id"])]
    return []

def send_message(login_name: str, *, role: str,
                 to_person_id: str,
                 text: Optional[str] = None,
                 file_path: Optional[str] = None) -> str:
    """
    Saves message to MongoDB. If file_path is given, stores via backend.lo_save_file and includes URL.
    """
    if (not text or text.strip() == "") and not file_path:
        raise ValueError("Provide text or attach a file.")

    me = _normalize_identity(login_name, role=role)
    if me["user_type"] not in ("doctor", "patient"):
        raise PermissionError("Only doctors or patients can send messages.")

    # Persist file via the same LO helper so it lives in ./files
    file_url = None
    if file_path:
        oid = backend.lo_save_file(file_path)
        file_url = f"files/{Path(str(oid)).name}" if "/" in str(oid) else f"files/{oid}"

    # Determine receiver_type
    if me["user_type"] == "doctor":
        receiver_type = "patient"
    else:
        receiver_type = "doctor"

    doc = {
        "sender_id": me["person_id"],
        "sender_type": me["user_type"],           # "doctor" or "patient"
        "receiver_id": to_person_id,
        "receiver_type": receiver_type,
        "text": (text or "").strip() or None,
        "file_url": file_url,
        "created_at": _now_iso(),
        # For efficient conversation lookups (unordered pair)
        "participants": sorted([me["person_id"], to_person_id]),
    }
    res = _messages.insert_one(doc)
    return str(res.inserted_id)

def get_conversation(login_name: str, *, role: str, other_person_id: str,
                     limit: int = 200) -> List[Dict[str, Any]]:
    """
    Returns messages for two-way conversation sorted ascending by time.
    """
    me = _normalize_identity(login_name, role=role)
    if me["user_type"] not in ("doctor", "patient"):
        return []

    parts = sorted([me["person_id"], other_person_id])
    cur = _messages.find({"participants": parts}).sort("created_at", ASCENDING).limit(limit)
    out = []
    for m in cur:
        out.append({
            "id": str(m["_id"]),
            "sender_id": m["sender_id"],
            "sender_type": m["sender_type"],
            "receiver_id": m["receiver_id"],
            "receiver_type": m["receiver_type"],
            "text": m.get("text"),
            "file_url": m.get("file_url"),
            "created_at": m["created_at"].strftime("%Y-%m-%d %H:%M:%S UTC"),
        })
    return out
