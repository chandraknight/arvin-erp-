from erp_billing_engine.config.env_config import *


def filter_by_fiscal_year(queryset, fiscal_year, date_field='created_at'):
    """
    Filters a queryset by the given fiscal year (start_date, end_date) on the specified date field.
    """
    if fiscal_year:
        filter_kwargs = {
            f'{date_field}__gte': fiscal_year.start_date,
            f'{date_field}__lte': fiscal_year.end_date,
        }
        return queryset.filter(**filter_kwargs)
    return queryset

def get_latest_tag():
    log_path = DEPLOY_TAG_PATH
    if log_path is False:
        return "V0.0.1"

    if not log_path or not os.path.exists(log_path):
        return "V0.0.2"

    with open(log_path, "r") as f:
        lines = f.readlines()

    for line in reversed(lines):
        if "Tag created:" in line:
            return line.strip().split("Tag created:")[-1].strip()

    return "V0.0.3"