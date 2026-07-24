from apps.reports.report_registry import get_user_visible_reports, get_dashboard_sections


def sidebar_reports(request):
    """Expose the same registry-driven, company-type/module-aware report sections
    used by the reports dashboard, so the sidebar menu doesn't drift out of sync."""
    user = getattr(request, 'user', None)
    company = getattr(request, 'user_company', None)
    if not user or not user.is_authenticated:
        return {'sidebar_report_sections': []}

    visible = get_user_visible_reports(user, company)
    return {'sidebar_report_sections': get_dashboard_sections(visible)}
