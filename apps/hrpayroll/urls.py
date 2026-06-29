from django.urls import path
from . import views

app_name = 'hrpayroll'

urlpatterns = [
    path('dashboard/', views.hrpayroll_dashboard, name='hrpayroll_dashboard'),

    # Department
    path('departments/', views.DepartmentListView.as_view(), name='department_list'),
    path('departments/create/', views.DepartmentCreateView.as_view(), name='department_create'),
    path('departments/<uuid:pk>/update/', views.DepartmentUpdateView.as_view(), name='department_update'),
    path('departments/<uuid:pk>/delete/', views.DepartmentDeleteView.as_view(), name='department_delete'),

    # Employee
    path('employees/', views.EmployeeListView.as_view(), name='employee_list'),
    path('employees/create/', views.EmployeeCreateView.as_view(), name='employee_create'),
    path('employees/<uuid:pk>/', views.EmployeeDetailView.as_view(), name='employee_detail'),
    path('employees/<uuid:pk>/update/', views.EmployeeUpdateView.as_view(), name='employee_update'),
    path('employees/<uuid:pk>/delete/', views.EmployeeDeleteView.as_view(), name='employee_delete'),
    path('employees/<uuid:employee_pk>/separate/', views.employee_separate, name='employee_separate'),

    # Employee sub-resources (documents, notes)
    path('employees/<uuid:employee_pk>/documents/add/', views.employee_document_create, name='employee_document_create'),
    path('employees/documents/<uuid:pk>/delete/', views.employee_document_delete, name='employee_document_delete'),
    path('employees/<uuid:employee_pk>/notes/add/', views.employee_note_create, name='employee_note_create'),
    path('employees/notes/<uuid:pk>/delete/', views.employee_note_delete, name='employee_note_delete'),

    # Earning
    path('earnings/', views.EarningListView.as_view(), name='earning_list'),
    path('earnings/create/', views.EarningCreateView.as_view(), name='earning_create'),
    path('earnings/<uuid:pk>/update/', views.EarningUpdateView.as_view(), name='earning_update'),
    path('earnings/<uuid:pk>/delete/', views.EarningDeleteView.as_view(), name='earning_delete'),

    # Deduction
    path('deductions/', views.DeductionListView.as_view(), name='deduction_list'),
    path('deductions/create/', views.DeductionCreateView.as_view(), name='deduction_create'),
    path('deductions/<uuid:pk>/update/', views.DeductionUpdateView.as_view(), name='deduction_update'),
    path('deductions/<uuid:pk>/delete/', views.DeductionDeleteView.as_view(), name='deduction_delete'),

    # Payroll Run
    path('payroll-runs/', views.PayrollRunListView.as_view(), name='payrollrun_list'),
    path('payroll-runs/create/', views.PayrollRunCreateView.as_view(), name='payrollrun_create'),
    path('payroll-runs/<uuid:pk>/update/', views.PayrollRunUpdateView.as_view(), name='payrollrun_update'),
    path('payroll-runs/<uuid:pk>/delete/', views.PayrollRunDeleteView.as_view(), name='payrollrun_delete'),
    path('payroll-runs/<uuid:pk>/generate-payslips/', views.generate_payslips, name='generate_payslips'),

    # Attendance
    path('attendance/', views.AttendanceListView.as_view(), name='attendance_list'),
    path('attendance/bulk-upload/', views.attendance_bulk_upload, name='attendance_bulk_upload'),
    path('attendance/create/', views.AttendanceCreateView.as_view(), name='attendance_create'),
    path('attendance/<uuid:pk>/update/', views.AttendanceUpdateView.as_view(), name='attendance_update'),
    path('attendance/<uuid:pk>/delete/', views.AttendanceDeleteView.as_view(), name='attendance_delete'),

    # Payslip
    path('payslips/', views.PayslipListView.as_view(), name='payslip_list'),
    path('payslips/create/', views.PayslipCreateView.as_view(), name='payslip_create'),
    path('payslips/<uuid:pk>/detail/', views.PayslipDetailView.as_view(), name='payslip_detail'),
    path('payslips/<uuid:pk>/update/', views.PayslipUpdateView.as_view(), name='payslip_update'),
    path('payslips/<uuid:pk>/delete/', views.PayslipDeleteView.as_view(), name='payslip_delete'),

    # Recruitment — Job Positions
    path('recruitment/positions/', views.JobPositionListView.as_view(), name='job_position_list'),
    path('recruitment/positions/create/', views.JobPositionCreateView.as_view(), name='job_position_create'),
    path('recruitment/positions/<uuid:pk>/update/', views.JobPositionUpdateView.as_view(), name='job_position_update'),

    # Recruitment — Applications
    path('recruitment/applications/', views.JobApplicationListView.as_view(), name='application_list'),
    path('recruitment/applications/create/', views.JobApplicationCreateView.as_view(), name='application_create'),
    path('recruitment/applications/<uuid:pk>/', views.JobApplicationDetailView.as_view(), name='application_detail'),
    path('recruitment/applications/<uuid:pk>/update/', views.JobApplicationUpdateView.as_view(), name='application_update'),
    path('recruitment/applications/<uuid:pk>/move/', views.application_move_stage, name='application_move_stage'),
    path('recruitment/applications/<uuid:pk>/hire/', views.hire_applicant, name='hire_applicant'),

    # Interviews
    path('recruitment/applications/<uuid:application_pk>/interviews/add/', views.interview_create, name='interview_create'),
    path('recruitment/interviews/<uuid:pk>/update/', views.interview_update_result, name='interview_update'),

    # Leave Management
    path('leave/types/', views.LeaveTypeListView.as_view(), name='leave_type_list'),
    path('leave/types/create/', views.LeaveTypeCreateView.as_view(), name='leave_type_create'),
    path('leave/types/<uuid:pk>/update/', views.LeaveTypeUpdateView.as_view(), name='leave_type_update'),
    path('leave/requests/', views.LeaveRequestListView.as_view(), name='leave_request_list'),
    path('leave/requests/create/', views.LeaveRequestCreateView.as_view(), name='leave_request_create'),
    path('leave/requests/<uuid:pk>/action/', views.leave_request_approve, name='leave_request_action'),

    # Performance Reviews
    path('performance/reviews/', views.PerformanceReviewListView.as_view(), name='review_list'),
    path('performance/reviews/create/', views.PerformanceReviewCreateView.as_view(), name='review_create'),
    path('performance/reviews/<uuid:pk>/update/', views.PerformanceReviewUpdateView.as_view(), name='review_update'),

    # Reports
    path('reports/payroll-summary/', views.PayrollSummaryReportView.as_view(), name='payroll_summary_report'),
    path('reports/monthly-attendance/', views.MonthlyAttendanceReportView.as_view(), name='monthly_attendance_report'),

    # Payslip PDF download (stub — view exists, PDF library not yet wired)
    path('payslips/<uuid:pk>/pdf/', views.download_payslip_pdf, name='download_payslip_pdf'),
]