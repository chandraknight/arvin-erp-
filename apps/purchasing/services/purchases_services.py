import uuid
from datetime import date


def generate_po_number() -> str:
    today = date.today().strftime("%Y%m%d")
    unique_part = uuid.uuid4().hex[:4].upper()
    return f"PO-{today}-{unique_part}"