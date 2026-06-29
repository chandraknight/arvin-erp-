from django import forms
from .models import (
    Department, Employee, Earning, Deduction, PayrollRun, Payslip, Attendance,
    JobPosition, JobApplication, Interview, LeaveType, LeaveRequest,
    EmployeeDocument, PerformanceReview, EmployeeNote, Separation,
)
from apps.utils.nepali_date import NepaliDateWidget, NepaliDateField, FiscalYearDateMixin


class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ['name', 'description']
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}


class EmployeeForm(FiscalYearDateMixin, forms.ModelForm):
    hire_date = NepaliDateField(widget=NepaliDateWidget(), required=True, label='Hire Date (BS)')
    date_of_birth = NepaliDateField(widget=NepaliDateWidget(), required=False, label='Date of Birth (BS)')
    probation_end_date = NepaliDateField(widget=NepaliDateWidget(), required=False, label='Probation End Date (BS)')

    class Meta:
        model = Employee
        fields = [
            'employee_id', 'department', 'first_name', 'last_name', 'email',
            'phone_number', 'gender', 'date_of_birth', 'address', 'profile_photo',
            'hire_date', 'employment_type', 'probation_end_date',
            'salary', 'hourly_rate', 'position', 'is_active',
            'emergency_contact_name', 'emergency_contact_phone', 'emergency_contact_relation',
        ]
        widgets = {
            'address': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        self.inject_fiscal_year(self.request)


class EarningForm(forms.ModelForm):
    class Meta:
        model = Earning
        fields = ['name', 'is_taxable']


class DeductionForm(forms.ModelForm):
    class Meta:
        model = Deduction
        fields = ['name', 'is_pre_tax']


class PayrollRunForm(FiscalYearDateMixin, forms.ModelForm):
    payroll_date      = NepaliDateField(widget=NepaliDateWidget(), required=True, label='Payroll Date (BS)')
    period_start_date = NepaliDateField(widget=NepaliDateWidget(), required=True, label='Period Start (BS)')
    period_end_date   = NepaliDateField(widget=NepaliDateWidget(), required=True, label='Period End (BS)')

    class Meta:
        model = PayrollRun
        fields = ['payroll_date', 'period_start_date', 'period_end_date', 'status']

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        self.inject_fiscal_year(self.request)


class AttendanceForm(FiscalYearDateMixin, forms.ModelForm):
    date = NepaliDateField(widget=NepaliDateWidget(), required=True, label='Date (BS)')

    class Meta:
        model = Attendance
        fields = ['employee', 'date', 'status', 'check_in_time', 'check_out_time', 'notes']
        widgets = {
            'check_in_time':  forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'check_out_time': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'notes':          forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        self.inject_fiscal_year(self.request)


class PayslipForm(FiscalYearDateMixin, forms.ModelForm):
    issue_date = NepaliDateField(widget=NepaliDateWidget(), required=True, label='Issue Date (BS)')

    class Meta:
        model = Payslip
        fields = ['payroll_run', 'employee', 'issue_date', 'is_finalized']

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        self.inject_fiscal_year(self.request)


# ── New forms ─────────────────────────────────────────────────────────────────

class JobPositionForm(forms.ModelForm):
    posted_date  = NepaliDateField(widget=NepaliDateWidget(), required=False, label='Posted Date (BS)')
    closing_date = NepaliDateField(widget=NepaliDateWidget(), required=False, label='Closing Date (BS)')

    class Meta:
        model = JobPosition
        fields = [
            'department', 'title', 'description', 'requirements',
            'employment_type', 'salary_min', 'salary_max', 'headcount',
            'status', 'posted_date', 'closing_date', 'location',
        ]
        widgets = {
            'description':  forms.Textarea(attrs={'rows': 3}),
            'requirements': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)


class JobApplicationForm(forms.ModelForm):
    class Meta:
        model = JobApplication
        fields = [
            'position', 'candidate_name', 'candidate_email', 'candidate_phone',
            'resume', 'cover_letter', 'source', 'status', 'notes',
        ]
        widgets = {
            'cover_letter': forms.Textarea(attrs={'rows': 3}),
            'notes':        forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        if self.request and not self.request.user.is_superuser:
            self.fields['position'].queryset = JobPosition.active_objects.filter(
                company=self.request.user_company
            )


class InterviewForm(forms.ModelForm):
    class Meta:
        model = Interview
        fields = [
            'interview_type', 'scheduled_at', 'duration_minutes',
            'interviewer_name', 'location_or_link', 'result', 'feedback',
        ]
        widgets = {
            'scheduled_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'feedback':     forms.Textarea(attrs={'rows': 3}),
        }


class LeaveTypeForm(forms.ModelForm):
    class Meta:
        model = LeaveType
        fields = [
            'name', 'days_allowed_per_year', 'is_paid',
            'carry_forward', 'requires_approval', 'description',
        ]


class LeaveRequestForm(FiscalYearDateMixin, forms.ModelForm):
    start_date = NepaliDateField(widget=NepaliDateWidget(), required=True, label='Start Date (BS)')
    end_date   = NepaliDateField(widget=NepaliDateWidget(), required=True, label='End Date (BS)')

    class Meta:
        model = LeaveRequest
        fields = ['employee', 'leave_type', 'start_date', 'end_date', 'days_requested', 'reason']
        widgets = {'reason': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        if self.request and not self.request.user.is_superuser:
            company = self.request.user_company
            self.fields['employee'].queryset = Employee.active_objects.filter(company=company)
            self.fields['leave_type'].queryset = LeaveType.active_objects.filter(company=company)
        self.inject_fiscal_year(self.request)


class EmployeeDocumentForm(forms.ModelForm):
    expiry_date = NepaliDateField(widget=NepaliDateWidget(), required=False, label='Expiry Date (BS)')

    class Meta:
        model = EmployeeDocument
        fields = ['document_type', 'title', 'file', 'expiry_date', 'notes']


class PerformanceReviewForm(FiscalYearDateMixin, forms.ModelForm):
    review_period_start = NepaliDateField(widget=NepaliDateWidget(), required=True, label='Period Start (BS)')
    review_period_end   = NepaliDateField(widget=NepaliDateWidget(), required=True, label='Period End (BS)')

    class Meta:
        model = PerformanceReview
        fields = [
            'employee', 'review_period_start', 'review_period_end',
            'overall_rating', 'goals_achieved', 'strengths',
            'areas_for_improvement', 'next_period_goals',
            'reviewer_comments', 'employee_comments', 'status',
        ]
        widgets = {
            'goals_achieved':         forms.Textarea(attrs={'rows': 2}),
            'strengths':              forms.Textarea(attrs={'rows': 2}),
            'areas_for_improvement':  forms.Textarea(attrs={'rows': 2}),
            'next_period_goals':      forms.Textarea(attrs={'rows': 2}),
            'reviewer_comments':      forms.Textarea(attrs={'rows': 2}),
            'employee_comments':      forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        if self.request and not self.request.user.is_superuser:
            self.fields['employee'].queryset = Employee.active_objects.filter(
                company=self.request.user_company
            )
        self.inject_fiscal_year(self.request)


class EmployeeNoteForm(forms.ModelForm):
    class Meta:
        model = EmployeeNote
        fields = ['note_type', 'title', 'content', 'is_confidential']
        widgets = {'content': forms.Textarea(attrs={'rows': 3})}


class SeparationForm(FiscalYearDateMixin, forms.ModelForm):
    effective_date = NepaliDateField(widget=NepaliDateWidget(), required=True, label='Effective Date (BS)')
    notice_date    = NepaliDateField(widget=NepaliDateWidget(), required=False, label='Notice Date (BS)')

    class Meta:
        model = Separation
        fields = [
            'separation_type', 'effective_date', 'notice_date', 'reason',
            'exit_interview_done', 'exit_interview_notes',
            'final_settlement_amount', 'assets_returned', 'rehire_eligible',
        ]
        widgets = {
            'reason':               forms.Textarea(attrs={'rows': 2}),
            'exit_interview_notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        self.inject_fiscal_year(self.request)
