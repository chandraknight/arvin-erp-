import datetime
import uuid

def generate_4_digit_code():
    now = datetime.datetime.now()
    time_component = now.microsecond
    uuid_component = uuid.uuid4().hex[-4:]
    combined_int = (time_component + int(uuid_component, 16)) % 10000
    return f"{combined_int:04d}"

def generate_6_digit_code():
    now = datetime.datetime.now()
    time_component = now.microsecond
    uuid_component = uuid.uuid4().hex[-4:]
    combined_int = (time_component + int(uuid_component, 16)) % 1000000
    return f"{combined_int:06d}"