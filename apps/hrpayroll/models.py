from django.db import models
from decimal import Decimal
from apps.utils.baseModel import BaseModel


# ── Choices ───────────────────────────────────────────────────────────────────

GENDER_CHOICES = [
    ('M', 'Male'),
    ('F', 'Female'),
    ('O', 'Other'),
    ('N', 'Prefer not to say'),
]

EMPLOYMENT_TYPE_CHOICES = [
    ('FULL_TIME',   'Full-Time'),
    ('PART_TIME',   'Part-Time'),
    ('CONTRACT',    'Contract'),
    ('INTERN',      'Intern'),
    ('PROBATION',   'Probation'),
    ('CONSULTANT',  'Consultant'),
]

APPLICATION_STATUS_CHOICES = [
    ('APPLIED',     'Applied'),
    ('SCREENING',   'Screening'),
    ('INTERVIEW',   'Interview Scheduled'),
    ('OFFER',       'Offer Extended'),
    ('HIRED',       'Hired'),
    ('REJECTED',    'Rejected'),
    ('WITHDRAWN',   'Withdrawn'),
]

INTERVIEW_TYPE_CHOICES = [
    ('PHONE',       'Phone Screen'),
    ('VIDEO',       'Video Call'),
    ('ONSITE',      'On-Site'),
    ('TECHNICAL',   'Technical'),
    ('HR',          'HR Round'),
    ('FINAL',       'Final Round'),
]

INTERVIEW_RESULT_CHOICES = [
    ('PENDING',     'Pending'),
    ('PASS',        'Pass'),
    ('FAIL',        'Fail'),
    ('NO_SHOW',     'No Show'),
]

LEAVE_STATUS_CHOICES = [
    ('PENDING',     'Pending'),
    ('APPROVED',    'Approved'),
    ('REJECTED',    'Rejected'),
    ('CANCELLED',   'Cancelled'),
]

DOCUMENT_TYPE_CHOICES = [
    ('CONTRACT',        'Employment Contract'),
    ('ID',              'Identity Document'),
    ('CERTIFICATE',     'Certificate / Degree'),
    ('OFFER_LETTER',    'Offer Letter'),
    ('NDA',             'NDA / Agreement'),
    ('PERFORMANCE',     'Performance Review'),
    ('WARNING',         'Warning Letter'),
    ('OTHER',           'Other'),
]

REVIEW_STATUS_CHOICES = [
    ('DRAFT',       'Draft'),
    ('SUBMITTED',   'Submitted'),
    ('ACKNOWLEDGED','Acknowledged'),
]

RATING_CHOICES = [
    (1, '1 — Needs Improvement'),
    (2, '2 — Below Expectations'),
    (3, '3 — Meets Expectations'),
    (4, '4 — Exceeds Expectations'),
    (5, '5 — Outstanding'),
]

NOTE_TYPE_CHOICES = [
    ('GENERAL',         'General Note'),
    ('WARNING',         'Warning'),
    ('COMMENDATION',    'Commendation'),
    ('DISCIPLINARY',    'Disciplinary Action'),
    ('PIP',             'Performance Improvement Plan'),
]

SEPARATION_TYPE_CHOICES = [
    ('RESIGNATION',     'Resignation'),
    ('TERMINATION',     'Termination'),
    ('REDUNDANCY',      'Redundancy / Layoff'),
    ('RETIREMENT',      'Retirement'),
    ('CONTRACT_END',    'Contract End'),
    ('MUTUAL',          'Mutual Agreement'),
]

JOB_STATUS_CHOICES = [
    ('OPEN',        'Open'),
    ('ON_HOLD',     'On Hold'),
    ('CLOSED',      'Closed'),
    ('FILLED',      'Filled'),
]


# ── Existing models (unchanged) ───────────────────────────────────────────────

class Department(BaseModel):
    company = models.ForeignKey(
        'company.Company', on_delete=models.CASCADE,
        related_name='departments', null=True, blank=True,
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'name'],
                name='unique_department_name_per_company',
            ),
        ]

    def __str__(self):
        return self.name


class Employee(BaseModel):
    company = models.ForeignKey('company.Company', on_delete=models.CASCADE, related_name='employees')
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name='employees')

    # Core identity
    employee_id = models.CharField(
        max_length=30, blank=True, null=True,
        help_text='Internal employee ID / badge number.'
    )
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, blank=True, null=True)
    date_of_birth = models.DateField(null=True, blank=True)
    address = models.TextField(blank=True, null=True)
    profile_photo = models.ImageField(upload_to='employee_photos/', blank=True, null=True)

    # Employment
    hire_date = models.DateField()
    employment_type = models.CharField(
        max_length=15, choices=EMPLOYMENT_TYPE_CHOICES, default='FULL_TIME'
    )
    probation_end_date = models.DateField(null=True, blank=True)
    salary = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    position = models.CharField(max_length=100, blank=True, null=True)
    is_active = models.BooleanField(default=True)

    # Emergency contact
    emergency_contact_name = models.CharField(max_length=150, blank=True, null=True)
    emergency_contact_phone = models.CharField(max_length=20, blank=True, null=True)
    emergency_contact_relation = models.CharField(max_length=50, blank=True, null=True)

    # Separation (set when employee leaves)
    termination_date = models.DateField(null=True, blank=True)
    termination_reason = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"


class Earning(BaseModel):
    name = models.CharField(max_length=100, unique=True)
    is_taxable = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Deduction(BaseModel):
    name = models.CharField(max_length=100, unique=True)
    is_pre_tax = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class PayrollRun(BaseModel):
    company = models.ForeignKey('company.Company', on_delete=models.CASCADE, related_name='payroll_runs')
    run_number = models.CharField(
        max_length=30, blank=True,
        help_text='Auto-generated sequential run number, e.g. PR-2081-001',
    )
    payroll_date = models.DateField(help_text="The date this payroll run is conducted.")
    period_start_date = models.DateField()
    period_end_date = models.DateField()
    total_gross_pay = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    total_net_pay = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    status = models.CharField(max_length=50, default='Draft', choices=(
        ('Draft', 'Draft'),
        ('Approved', 'Approved'),
        ('Processed', 'Processed'),
        ('Paid', 'Paid'),
    ))

    class Meta:
        unique_together = ('company', 'period_start_date', 'period_end_date')
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'run_number'],
                condition=models.Q(run_number__gt=''),
                name='unique_payroll_run_number_per_company',
            ),
        ]
        ordering = ['-period_start_date']

    def save(self, *args, **kwargs):
        if not self.run_number and self.company_id:
            import nepali_datetime
            from django.db import transaction
            np_year = nepali_datetime.date.today().year
            prefix = f"PR-{np_year}-"
            with transaction.atomic():
                # select_for_update serializes concurrent run-number assignment
                last = (
                    PayrollRun.objects.select_for_update()
                    .filter(company_id=self.company_id, run_number__startswith=prefix)
                    .order_by('-run_number')
                    .first()
                )
                seq = 1
                if last and last.run_number:
                    try:
                        seq = int(last.run_number.rsplit('-', 1)[-1]) + 1
                    except (ValueError, IndexError):
                        pass
                self.run_number = f"{prefix}{seq:03d}"
                super().save(*args, **kwargs)
            return
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.run_number or 'PayrollRun'}: {self.period_start_date} – {self.period_end_date} ({self.company.name})"


class Payslip(BaseModel):
    payroll_run = models.ForeignKey(PayrollRun, on_delete=models.CASCADE, related_name='payslips')
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='payslips')
    gross_pay = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    total_deductions = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    net_pay = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    issue_date = models.DateField()
    is_finalized = models.BooleanField(default=False)

    class Meta:
        unique_together = ('payroll_run', 'employee')
        ordering = ['issue_date', 'employee__last_name']

    def __str__(self):
        return f"Payslip for {self.employee.full_name} ({self.payroll_run.period_start_date} - {self.payroll_run.period_end_date})"


class PayslipEarning(BaseModel):
    payslip = models.ForeignKey(Payslip, on_delete=models.CASCADE, related_name='payslip_earnings')
    earning = models.ForeignKey(Earning, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.earning.name}: {self.amount}"


class PayslipDeduction(BaseModel):
    payslip = models.ForeignKey(Payslip, on_delete=models.CASCADE, related_name='payslip_deductions')
    deduction = models.ForeignKey(Deduction, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.deduction.name}: {self.amount}"


class Attendance(BaseModel):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='attendance_records')
    date = models.DateField()
    status = models.CharField(max_length=50, choices=(
        ('Present', 'Present'),
        ('Absent', 'Absent'),
        ('Leave', 'Leave'),
        ('Holiday', 'Holiday'),
    ), default='Present')
    check_in_time = models.DateTimeField(null=True, blank=True)
    check_out_time = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ('employee', 'date')
        ordering = ['date', 'employee__last_name']

    def __str__(self):
        return f"{self.employee.full_name} - {self.date} ({self.status})"


# ── New models ────────────────────────────────────────────────────────────────

class JobPosition(BaseModel):
    """
    An open job requisition. Drives the recruitment pipeline.
    """
    company = models.ForeignKey('company.Company', on_delete=models.CASCADE, related_name='job_positions')
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name='job_positions')
    title = models.CharField(max_length=150)
    description = models.TextField(blank=True, null=True)
    requirements = models.TextField(blank=True, null=True, help_text='Skills, qualifications, experience required.')
    employment_type = models.CharField(max_length=15, choices=EMPLOYMENT_TYPE_CHOICES, default='FULL_TIME')
    salary_min = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    salary_max = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    headcount = models.PositiveSmallIntegerField(default=1, help_text='Number of positions to fill.')
    status = models.CharField(max_length=10, choices=JOB_STATUS_CHOICES, default='OPEN')
    posted_date = models.DateField(null=True, blank=True)
    closing_date = models.DateField(null=True, blank=True)
    location = models.CharField(max_length=150, blank=True, null=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} ({self.company.name})"

    @property
    def application_count(self):
        return self.applications.count()

    @property
    def hired_count(self):
        return self.applications.filter(status='HIRED').count()


class JobApplication(BaseModel):
    """
    A candidate's application for a JobPosition.
    Lifecycle: APPLIED → SCREENING → INTERVIEW → OFFER → HIRED / REJECTED
    """
    company = models.ForeignKey('company.Company', on_delete=models.CASCADE, related_name='job_applications')
    position = models.ForeignKey(JobPosition, on_delete=models.CASCADE, related_name='applications')

    # Candidate info
    candidate_name = models.CharField(max_length=150)
    candidate_email = models.EmailField()
    candidate_phone = models.CharField(max_length=20, blank=True, null=True)
    resume = models.FileField(upload_to='resumes/', blank=True, null=True)
    cover_letter = models.TextField(blank=True, null=True)
    source = models.CharField(
        max_length=50, blank=True, null=True,
        help_text='Where the candidate came from (LinkedIn, Referral, Walk-in, etc.)'
    )

    status = models.CharField(max_length=10, choices=APPLICATION_STATUS_CHOICES, default='APPLIED')
    applied_date = models.DateField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True, help_text='Internal HR notes on this application.')

    # If hired, link to the created employee record
    hired_employee = models.OneToOneField(
        Employee, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='job_application'
    )

    class Meta:
        ordering = ['-applied_date']

    def __str__(self):
        return f"{self.candidate_name} → {self.position.title}"


class Interview(BaseModel):
    """
    A scheduled interview for a job application.
    """
    application = models.ForeignKey(JobApplication, on_delete=models.CASCADE, related_name='interviews')
    interview_type = models.CharField(max_length=15, choices=INTERVIEW_TYPE_CHOICES, default='HR')
    scheduled_at = models.DateTimeField()
    duration_minutes = models.PositiveSmallIntegerField(default=60)
    interviewer_name = models.CharField(max_length=150, blank=True, null=True)
    location_or_link = models.CharField(
        max_length=255, blank=True, null=True,
        help_text='Room number, address, or video call link.'
    )
    result = models.CharField(max_length=10, choices=INTERVIEW_RESULT_CHOICES, default='PENDING')
    feedback = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['scheduled_at']

    def __str__(self):
        return f"{self.get_interview_type_display()} for {self.application.candidate_name} on {self.scheduled_at:%Y-%m-%d}"


class LeaveType(BaseModel):
    """
    A type of leave (Annual, Sick, Maternity, etc.) — company-scoped.
    """
    company = models.ForeignKey('company.Company', on_delete=models.CASCADE, related_name='leave_types')
    name = models.CharField(max_length=100)
    days_allowed_per_year = models.PositiveSmallIntegerField(default=0)
    is_paid = models.BooleanField(default=True)
    carry_forward = models.BooleanField(default=False, help_text='Allow unused days to carry forward to next year.')
    requires_approval = models.BooleanField(default=True)
    description = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        unique_together = ('company', 'name')
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.company.name})"


class LeaveBalance(BaseModel):
    """
    Tracks how many leave days an employee has remaining for a given leave type and year.
    """
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='leave_balances')
    leave_type = models.ForeignKey(LeaveType, on_delete=models.CASCADE, related_name='balances')
    year = models.PositiveSmallIntegerField()
    allocated = models.DecimalField(max_digits=5, decimal_places=1, default=Decimal('0.0'))
    used = models.DecimalField(max_digits=5, decimal_places=1, default=Decimal('0.0'))
    carried_forward = models.DecimalField(max_digits=5, decimal_places=1, default=Decimal('0.0'))

    class Meta:
        unique_together = ('employee', 'leave_type', 'year')

    @property
    def remaining(self):
        return self.allocated + self.carried_forward - self.used

    def __str__(self):
        return f"{self.employee.full_name} — {self.leave_type.name} {self.year}"


class LeaveRequest(BaseModel):
    """
    An employee's request for leave. Requires approval if leave_type.requires_approval=True.
    """
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='leave_requests')
    leave_type = models.ForeignKey(LeaveType, on_delete=models.CASCADE, related_name='requests')
    start_date = models.DateField()
    end_date = models.DateField()
    days_requested = models.DecimalField(max_digits=5, decimal_places=1)
    reason = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=10, choices=LEAVE_STATUS_CHOICES, default='PENDING')
    approved_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='approved_leave_requests'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-start_date']

    def __str__(self):
        return f"{self.employee.full_name} — {self.leave_type.name} {self.start_date} to {self.end_date}"


class EmployeeDocument(BaseModel):
    """
    A document attached to an employee record (contract, ID, certificate, etc.).
    """
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='documents')
    document_type = models.CharField(max_length=15, choices=DOCUMENT_TYPE_CHOICES, default='OTHER')
    title = models.CharField(max_length=200)
    file = models.FileField(upload_to='employee_documents/')
    expiry_date = models.DateField(null=True, blank=True, help_text='For documents that expire (e.g. visas, certifications).')
    notes = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        ordering = ['document_type', '-created_at']

    def __str__(self):
        return f"{self.employee.full_name} — {self.title}"


class PerformanceReview(BaseModel):
    """
    A periodic performance review for an employee.
    """
    company = models.ForeignKey('company.Company', on_delete=models.CASCADE, related_name='performance_reviews')
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='performance_reviews')
    reviewer = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='conducted_reviews'
    )
    review_period_start = models.DateField()
    review_period_end = models.DateField()
    overall_rating = models.PositiveSmallIntegerField(choices=RATING_CHOICES, null=True, blank=True)
    goals_achieved = models.TextField(blank=True, null=True)
    strengths = models.TextField(blank=True, null=True)
    areas_for_improvement = models.TextField(blank=True, null=True)
    next_period_goals = models.TextField(blank=True, null=True)
    reviewer_comments = models.TextField(blank=True, null=True)
    employee_comments = models.TextField(blank=True, null=True, help_text='Employee self-assessment or response.')
    status = models.CharField(max_length=15, choices=REVIEW_STATUS_CHOICES, default='DRAFT')

    class Meta:
        ordering = ['-review_period_end']

    def __str__(self):
        return f"Review: {self.employee.full_name} ({self.review_period_start} – {self.review_period_end})"


class EmployeeNote(BaseModel):
    """
    An HR note on an employee — warnings, commendations, disciplinary actions.
    """
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='hr_notes')
    note_type = models.CharField(max_length=15, choices=NOTE_TYPE_CHOICES, default='GENERAL')
    title = models.CharField(max_length=200)
    content = models.TextField()
    recorded_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='recorded_hr_notes'
    )
    is_confidential = models.BooleanField(default=False, help_text='Confidential notes are only visible to HR admins.')

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_note_type_display()}: {self.employee.full_name} — {self.title}"


class Separation(BaseModel):
    """
    Records an employee's departure — resignation, termination, retirement, etc.
    This is the formal "offboarding" record.
    """
    employee = models.OneToOneField(Employee, on_delete=models.CASCADE, related_name='separation')
    separation_type = models.CharField(max_length=15, choices=SEPARATION_TYPE_CHOICES)
    effective_date = models.DateField()
    notice_date = models.DateField(null=True, blank=True, help_text='Date notice was given.')
    reason = models.TextField(blank=True, null=True)
    exit_interview_done = models.BooleanField(default=False)
    exit_interview_notes = models.TextField(blank=True, null=True)
    final_settlement_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    assets_returned = models.BooleanField(default=False)
    rehire_eligible = models.BooleanField(default=True)
    processed_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='processed_separations'
    )

    class Meta:
        ordering = ['-effective_date']

    def __str__(self):
        return f"{self.get_separation_type_display()}: {self.employee.full_name} on {self.effective_date}"

