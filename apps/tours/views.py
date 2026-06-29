import logging
from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.utils.decorator import auth_required

from .forms import (
    TourDestinationForm, TourPackageForm, TourEnquiryForm,
    TourBookingForm, TourBookingItemFormSet,
    AirTicketForm, IATASourceFileForm, IATAAirlineForm, IATAAirportForm,
    AIRFileForm, BSPPaymentForm,
)
from .models import TourDestination, TourPackage, TourEnquiry, TourBooking, AirTicket, IATAAirline, IATAAirport, IATASourceFile, AIRFile, BSPPaymentRecord
from .services import issue_invoice_from_booking

logger = logging.getLogger(__name__)

_INPUT_CLASS = 'block w-full border border-gray-300 px-4 py-3 text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150'


def _require_tours(request):
    company = request.user_company
    if company and not getattr(company, 'enable_tours', False):
        messages.warning(request, "Tours & Ticketing module is not enabled for your company.")
        return redirect('accounts:user_dashboard')
    return None


# ── Dashboard ─────────────────────────────────────────────────────────────────

@auth_required('tours.view_tourenquiry')
def tours_dashboard(request):
    guard = _require_tours(request)
    if guard:
        return guard
    company = request.user_company
    context = {
        'total_enquiries': TourEnquiry.active_objects.filter(company=company).count(),
        'new_enquiries': TourEnquiry.active_objects.filter(company=company, status='NEW').count(),
        'total_bookings': TourBooking.active_objects.filter(company=company).count(),
        'confirmed_bookings': TourBooking.active_objects.filter(company=company, status='CONFIRMED').count(),
        'recent_enquiries': TourEnquiry.active_objects.filter(company=company).order_by('-created_at')[:5],
        'recent_bookings': TourBooking.active_objects.filter(company=company).order_by('-created_at')[:5],
    }
    return render(request, 'tours/dashboard.html', context)


# ── Destinations ──────────────────────────────────────────────────────────────

@auth_required('tours.view_tourdestination')
def destination_list(request):
    guard = _require_tours(request)
    if guard:
        return guard
    company = request.user_company
    qs = TourDestination.active_objects.filter(company=company).order_by('name')
    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'tours/destination_list.html', {'page_obj': page_obj})


@auth_required('tours.add_tourdestination')
def destination_create(request):
    guard = _require_tours(request)
    if guard:
        return guard
    form = TourDestinationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        dest = form.save(commit=False)
        dest.company = request.user_company
        dest.created_by = request.user
        dest.save()
        messages.success(request, f'Destination "{dest.name}" created.')
        return redirect('tours:destination_list')
    return render(request, 'tours/destination_form.html', {'form': form, 'title': 'Add Destination'})


@auth_required('tours.change_tourdestination')
def destination_edit(request, pk):
    guard = _require_tours(request)
    if guard:
        return guard
    dest = get_object_or_404(TourDestination, pk=pk, company=request.user_company)
    form = TourDestinationForm(request.POST or None, instance=dest)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'Destination "{dest.name}" updated.')
        return redirect('tours:destination_list')
    return render(request, 'tours/destination_form.html', {'form': form, 'title': 'Edit Destination', 'object': dest})


# ── Packages ──────────────────────────────────────────────────────────────────

@auth_required('tours.view_tourpackage')
def package_list(request):
    guard = _require_tours(request)
    if guard:
        return guard
    company = request.user_company
    qs = TourPackage.active_objects.filter(company=company).select_related('destination').order_by('name')
    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'tours/package_list.html', {'page_obj': page_obj})


@auth_required('tours.add_tourpackage')
def package_create(request):
    guard = _require_tours(request)
    if guard:
        return guard
    company = request.user_company
    form = TourPackageForm(request.POST or None, company=company)
    if request.method == 'POST' and form.is_valid():
        pkg = form.save(commit=False)
        pkg.company = company
        pkg.created_by = request.user
        pkg.save()
        messages.success(request, f'Package "{pkg.name}" created.')
        return redirect('tours:package_list')
    return render(request, 'tours/package_form.html', {'form': form, 'title': 'Add Package'})


@auth_required('tours.change_tourpackage')
def package_edit(request, pk):
    guard = _require_tours(request)
    if guard:
        return guard
    company = request.user_company
    pkg = get_object_or_404(TourPackage, pk=pk, company=company)
    form = TourPackageForm(request.POST or None, instance=pkg, company=company)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'Package "{pkg.name}" updated.')
        return redirect('tours:package_list')
    return render(request, 'tours/package_form.html', {'form': form, 'title': 'Edit Package', 'object': pkg})


# ── Enquiries ─────────────────────────────────────────────────────────────────

@auth_required('tours.view_tourenquiry')
def enquiry_list(request):
    guard = _require_tours(request)
    if guard:
        return guard
    company = request.user_company
    qs = TourEnquiry.active_objects.filter(company=company).select_related('package', 'destination').order_by('-created_at')
    status_filter = request.GET.get('status', '')
    if status_filter:
        qs = qs.filter(status=status_filter)
    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'tours/enquiry_list.html', {
        'page_obj': page_obj,
        'status_filter': status_filter,
        'status_choices': TourEnquiry.ENQUIRY_STATUS_CHOICES,
    })


@auth_required('tours.add_tourenquiry')
def enquiry_create(request):
    guard = _require_tours(request)
    if guard:
        return guard
    company = request.user_company
    form = TourEnquiryForm(request.POST or None, company=company)
    if request.method == 'POST' and form.is_valid():
        enq = form.save(commit=False)
        enq.company = company
        enq.created_by = request.user
        enq.save()
        messages.success(request, f'Enquiry {enq.enquiry_number} created.')
        return redirect('tours:enquiry_detail', pk=enq.pk)
    return render(request, 'tours/enquiry_form.html', {'form': form, 'title': 'New Enquiry'})


@auth_required('tours.view_tourenquiry')
def enquiry_detail(request, pk):
    guard = _require_tours(request)
    if guard:
        return guard
    enq = get_object_or_404(TourEnquiry, pk=pk, company=request.user_company)
    return render(request, 'tours/enquiry_detail.html', {'enq': enq})


@auth_required('tours.change_tourenquiry')
def enquiry_edit(request, pk):
    guard = _require_tours(request)
    if guard:
        return guard
    company = request.user_company
    enq = get_object_or_404(TourEnquiry, pk=pk, company=company)
    form = TourEnquiryForm(request.POST or None, instance=enq, company=company)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Enquiry updated.')
        return redirect('tours:enquiry_detail', pk=enq.pk)
    return render(request, 'tours/enquiry_form.html', {'form': form, 'title': 'Edit Enquiry', 'object': enq})


@auth_required('tours.change_tourenquiry')
def enquiry_update_status(request, pk):
    """Quick status update from the detail page."""
    enq = get_object_or_404(TourEnquiry, pk=pk, company=request.user_company)
    new_status = request.POST.get('status')
    valid = [k for k, _ in TourEnquiry.ENQUIRY_STATUS_CHOICES]
    if new_status in valid:
        enq.status = new_status
        enq.save(update_fields=['status'])
        messages.success(request, f'Status updated to {enq.get_status_display()}.')
    return redirect('tours:enquiry_detail', pk=pk)


@auth_required('tours.add_tourbooking')
def enquiry_convert_to_booking(request, pk):
    """Convert an enquiry into a TourBooking."""
    guard = _require_tours(request)
    if guard:
        return guard
    company = request.user_company
    enq = get_object_or_404(TourEnquiry, pk=pk, company=company)

    if hasattr(enq, 'booking') and enq.booking:
        messages.info(request, 'This enquiry is already converted to a booking.')
        return redirect('tours:booking_detail', pk=enq.booking.pk)

    if enq.status == 'CONVERTED':
        messages.error(request, 'This enquiry is already converted. Cannot re-convert.')
        return redirect('tours:enquiry_detail', pk=pk)

    initial = {
        'contact_name': enq.contact_name,
        'contact_phone': enq.contact_phone,
        'contact_email': enq.contact_email,
        'customer': enq.customer,
        'travel_date': enq.travel_date,
        'return_date': enq.return_date,
        'num_adults': enq.num_adults,
        'num_children': enq.num_children,
        'special_requests': enq.special_requests,
    }
    form = TourBookingForm(request.POST or None, initial=initial, company=company)
    formset = TourBookingItemFormSet(request.POST or None, company=company)

    # Pre-populate item from package if set on enquiry
    if request.method == 'GET' and enq.package:
        from .forms import TourBookingItemForm
        formset = TourBookingItemFormSet(
            initial=[{
                'item_type': 'PACKAGE',
                'package': enq.package,
                'description': str(enq.package),
                'quantity': enq.num_adults + enq.num_children,
                'unit_price': enq.package.price_per_adult,
                'discount_percent': 0,
            }],
            company=company,
        )

    if request.method == 'POST' and form.is_valid() and formset.is_valid():
        booking = form.save(commit=False)
        booking.company = company
        booking.enquiry = enq
        booking.created_by = request.user
        booking.save()

        formset.instance = booking
        items = formset.save(commit=False)
        for item in items:
            item.booking = booking
            item.save()
        for item in formset.deleted_objects:
            item.delete()

        booking.recalculate_totals()

        enq.status = 'CONVERTED'
        enq.save(update_fields=['status'])

        messages.success(request, f'Booking {booking.booking_number} created from enquiry {enq.enquiry_number}.')
        return redirect('tours:booking_detail', pk=booking.pk)

    return render(request, 'tours/booking_form.html', {
        'form': form,
        'formset': formset,
        'title': f'Convert Enquiry {enq.enquiry_number} to Booking',
        'enquiry': enq,
    })


# ── Bookings ──────────────────────────────────────────────────────────────────

@auth_required('tours.view_tourbooking')
def booking_list(request):
    guard = _require_tours(request)
    if guard:
        return guard
    company = request.user_company
    qs = TourBooking.active_objects.filter(company=company).order_by('-created_at')
    status_filter = request.GET.get('status', '')
    if status_filter:
        qs = qs.filter(status=status_filter)
    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'tours/booking_list.html', {
        'page_obj': page_obj,
        'status_filter': status_filter,
        'status_choices': TourBooking.BOOKING_STATUS_CHOICES,
    })


@auth_required('tours.add_tourbooking')
def booking_create(request):
    guard = _require_tours(request)
    if guard:
        return guard
    company = request.user_company
    form = TourBookingForm(request.POST or None, company=company)
    formset = TourBookingItemFormSet(request.POST or None, company=company)
    if request.method == 'POST' and form.is_valid() and formset.is_valid():
        booking = form.save(commit=False)
        booking.company = company
        booking.created_by = request.user
        booking.save()
        formset.instance = booking
        items = formset.save(commit=False)
        for item in items:
            item.booking = booking
            item.save()
        for item in formset.deleted_objects:
            item.delete()
        booking.recalculate_totals()
        messages.success(request, f'Booking {booking.booking_number} created.')
        return redirect('tours:booking_detail', pk=booking.pk)
    return render(request, 'tours/booking_form.html', {
        'form': form, 'formset': formset, 'title': 'New Booking',
    })


@auth_required('tours.view_tourbooking')
def booking_detail(request, pk):
    guard = _require_tours(request)
    if guard:
        return guard
    booking = get_object_or_404(TourBooking, pk=pk, company=request.user_company)
    items = booking.items.filter(is_deleted=False)
    return render(request, 'tours/booking_detail.html', {'booking': booking, 'items': items})


@auth_required('tours.change_tourbooking')
def booking_edit(request, pk):
    guard = _require_tours(request)
    if guard:
        return guard
    company = request.user_company
    booking = get_object_or_404(TourBooking, pk=pk, company=company)
    form = TourBookingForm(request.POST or None, instance=booking, company=company)
    formset = TourBookingItemFormSet(request.POST or None, instance=booking, company=company)
    if request.method == 'POST' and form.is_valid() and formset.is_valid():
        form.save()
        items = formset.save(commit=False)
        for item in items:
            item.booking = booking
            item.save()
        for item in formset.deleted_objects:
            item.delete()
        booking.recalculate_totals()
        messages.success(request, 'Booking updated.')
        return redirect('tours:booking_detail', pk=booking.pk)
    return render(request, 'tours/booking_form.html', {
        'form': form, 'formset': formset,
        'title': f'Edit Booking {booking.booking_number}', 'object': booking,
    })


@auth_required('tours.change_tourbooking')
def booking_update_status(request, pk):
    booking = get_object_or_404(TourBooking, pk=pk, company=request.user_company)
    new_status = request.POST.get('status')
    valid = [k for k, _ in TourBooking.BOOKING_STATUS_CHOICES]
    if new_status in valid:
        booking.status = new_status
        booking.save(update_fields=['status'])
        messages.success(request, f'Status updated to {booking.get_status_display()}.')
    return redirect('tours:booking_detail', pk=pk)


@auth_required('tours.change_tourbooking')
def booking_issue_invoice(request, pk):
    """Issue a billing invoice from the booking."""
    guard = _require_tours(request)
    if guard:
        return guard
    booking = get_object_or_404(TourBooking, pk=pk, company=request.user_company)

    if booking.has_invoice:
        messages.info(request, 'Invoice already issued for this booking.')
        return redirect('billing:view_invoice_detail', pk=booking.invoice.pk)

    if not booking.items.filter(is_deleted=False).exists():
        messages.error(request, 'Cannot issue invoice: booking has no line items.')
        return redirect('tours:booking_detail', pk=pk)

    invoice = issue_invoice_from_booking(booking, request.user)
    messages.success(request, f'Invoice {invoice.invoice_number} issued successfully.')
    return redirect('billing:view_invoice_detail', pk=invoice.pk)


# ── Air Tickets ───────────────────────────────────────────────────────────────

@auth_required('tours.view_airticket')
def ticket_list(request):
    guard = _require_tours(request)
    if guard:
        return guard
    company = request.user_company
    qs = AirTicket.active_objects.filter(company=company).select_related('airline', 'origin', 'destination', 'booking').order_by('-issue_date')
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(ticket_number__icontains=q) | qs.filter(passenger_name__icontains=q) | qs.filter(pnr__icontains=q)
    status_filter = request.GET.get('status', '')
    if status_filter:
        qs = qs.filter(status=status_filter)
    paginator = Paginator(qs, 30)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'tours/ticket_list.html', {
        'page_obj': page_obj,
        'q': q,
        'status_filter': status_filter,
        'status_choices': AirTicket.TICKET_STATUS_CHOICES,
    })


@auth_required('tours.add_airticket')
def ticket_create(request):
    guard = _require_tours(request)
    if guard:
        return guard
    company = request.user_company
    form = AirTicketForm(request.POST or None, company=company)
    if request.method == 'POST' and form.is_valid():
        ticket = form.save(commit=False)
        ticket.company = company
        ticket.created_by = request.user
        ticket.save()
        messages.success(request, f'Ticket {ticket.ticket_number} created.')
        return redirect('tours:ticket_detail', pk=ticket.pk)
    return render(request, 'tours/ticket_form.html', {'form': form, 'title': 'Issue Air Ticket'})


@auth_required('tours.view_airticket')
def ticket_detail(request, pk):
    guard = _require_tours(request)
    if guard:
        return guard
    ticket = get_object_or_404(AirTicket, pk=pk, company=request.user_company)
    return render(request, 'tours/ticket_detail.html', {'ticket': ticket})


@auth_required('tours.change_airticket')
def ticket_edit(request, pk):
    guard = _require_tours(request)
    if guard:
        return guard
    company = request.user_company
    ticket = get_object_or_404(AirTicket, pk=pk, company=company)
    form = AirTicketForm(request.POST or None, instance=ticket, company=company)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Ticket updated.')
        return redirect('tours:ticket_detail', pk=ticket.pk)
    return render(request, 'tours/ticket_form.html', {'form': form, 'title': f'Edit Ticket {ticket.ticket_number}', 'object': ticket})


# ── IATA Reference: Airlines ──────────────────────────────────────────────────

@auth_required('tours.view_iataairline')
def airline_list(request):
    guard = _require_tours(request)
    if guard:
        return guard
    q = request.GET.get('q', '').strip()
    qs = IATAAirline.active_objects.order_by('iata_code')
    if q:
        qs = qs.filter(iata_code__icontains=q) | qs.filter(name__icontains=q)
    paginator = Paginator(qs, 50)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'tours/airline_list.html', {'page_obj': page_obj, 'q': q})


@auth_required('tours.add_iataairline')
def airline_create(request):
    if not request.user.is_superuser:
        messages.error(request, "Only superadmins can manage global IATA airline data.")
        return redirect('tours:airline_list')
    form = IATAAirlineForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Airline added.')
        return redirect('tours:airline_list')
    return render(request, 'tours/airline_form.html', {'form': form, 'title': 'Add Airline'})


@auth_required('tours.add_iataairline')
def airline_import(request):
    """Bulk-import airlines from CSV. Superadmin only — global reference data."""
    if not request.user.is_superuser:
        messages.error(request, "Only superadmins can import global IATA airline data.")
        return redirect('tours:airline_list')
    if request.method == 'POST' and request.FILES.get('file'):
        from .iata_services import import_iata_airlines_from_csv
        try:
            created, updated, skipped = import_iata_airlines_from_csv(request.FILES['file'])
            messages.success(request, f'Airlines imported: {created} created, {updated} updated, {skipped} skipped.')
        except Exception as e:
            messages.error(request, f'Import failed: {e}')
        return redirect('tours:airline_list')
    return render(request, 'tours/iata_import.html', {
        'title': 'Import IATA Airlines',
        'import_url': 'tours:airline_import',
        'description': 'Upload a CSV with columns: iata_code, name, country, icao_code',
        'sample_headers': 'iata_code,name,country,icao_code',
        'sample_row': 'QR,Qatar Airways,Qatar,QTAR',
    })


# ── IATA Reference: Airports ──────────────────────────────────────────────────

@auth_required('tours.view_iataairport')
def airport_list(request):
    guard = _require_tours(request)
    if guard:
        return guard
    q = request.GET.get('q', '').strip()
    qs = IATAAirport.active_objects.order_by('iata_code')
    if q:
        qs = qs.filter(iata_code__icontains=q) | qs.filter(name__icontains=q) | qs.filter(city__icontains=q)
    paginator = Paginator(qs, 50)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'tours/airport_list.html', {'page_obj': page_obj, 'q': q})


@auth_required('tours.add_iataairport')
def airport_import(request):
    """Bulk-import airports from CSV."""
    if request.method == 'POST' and request.FILES.get('file'):
        from .iata_services import import_iata_airports_from_csv
        try:
            created, updated, skipped = import_iata_airports_from_csv(request.FILES['file'])
            messages.success(request, f'Airports imported: {created} created, {updated} updated, {skipped} skipped.')
        except Exception as e:
            messages.error(request, f'Import failed: {e}')
        return redirect('tours:airport_list')
    return render(request, 'tours/iata_import.html', {
        'title': 'Import IATA Airports',
        'import_url': 'tours:airport_import',
        'description': 'Upload a CSV with columns: iata_code, name, city, country, country_code, icao_code, latitude, longitude',
        'sample_headers': 'iata_code,name,city,country,country_code,icao_code',
        'sample_row': 'KTM,Tribhuvan International Airport,Kathmandu,Nepal,NP,VNKT',
    })


# ── IATA BSP Reconciliation ───────────────────────────────────────────────────

@auth_required('tours.view_iatasourcefile')
def reconciliation_list(request):
    guard = _require_tours(request)
    if guard:
        return guard
    company = request.user_company
    qs = IATASourceFile.active_objects.filter(company=company).order_by('-created_at')
    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'tours/reconciliation_list.html', {'page_obj': page_obj})


@auth_required('tours.add_iatasourcefile')
def reconciliation_upload(request):
    guard = _require_tours(request)
    if guard:
        return guard
    company = request.user_company
    form = IATASourceFileForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        src = form.save(commit=False)
        src.company = company
        src.original_filename = request.FILES['file'].name
        src.uploaded_by = request.user
        src.created_by = request.user
        src.save()
        messages.success(request, f'File "{src.original_filename}" uploaded. Process it to run reconciliation.')
        return redirect('tours:reconciliation_detail', pk=src.pk)
    return render(request, 'tours/reconciliation_upload.html', {'form': form})


@auth_required('tours.view_iatasourcefile')
def reconciliation_detail(request, pk):
    guard = _require_tours(request)
    if guard:
        return guard
    src = get_object_or_404(IATASourceFile, pk=pk, company=request.user_company)
    items = src.items.select_related('air_ticket').order_by('match_status', 'raw_ticket_number')
    paginator = Paginator(items, 50)
    page_obj = paginator.get_page(request.GET.get('page'))
    match_filter = request.GET.get('match', '')
    if match_filter:
        items = items.filter(match_status=match_filter)
    return render(request, 'tours/reconciliation_detail.html', {
        'src': src,
        'page_obj': page_obj,
        'match_filter': match_filter,
    })


@auth_required('tours.change_iatasourcefile')
def reconciliation_process(request, pk):
    """Trigger processing/re-processing of a source file."""
    guard = _require_tours(request)
    if guard:
        return guard
    src = get_object_or_404(IATASourceFile, pk=pk, company=request.user_company)
    auto_import = request.POST.get('auto_import') == '1'
    from .iata_services import process_iata_source_file
    try:
        result = process_iata_source_file(src, auto_import=auto_import)
        if 'error' in result:
            messages.error(request, f'Processing failed: {result["error"]}')
        else:
            messages.success(
                request,
                f'Processed {result["total"]} rows — '
                f'{result["matched"]} matched, {result["mismatched"]} mismatched, '
                f'{result["unmatched"]} not found, {result["new_imported"]} imported.'
            )
    except Exception as e:
        logger.exception('IATA reconciliation error for file %s', pk)
        messages.error(request, f'Unexpected error: {e}')
    return redirect('tours:reconciliation_detail', pk=pk)


# ── AIR File (Agency Invoice Report) & Payment Reconciliation ─────────────────

@auth_required('tours.view_airfile')
def air_file_list(request):
    guard = _require_tours(request)
    if guard:
        return guard
    company = request.user_company
    qs = AIRFile.active_objects.filter(company=company).order_by('-period_to')

    status_filter = request.GET.get('status', '')
    if status_filter:
        qs = qs.filter(payment_status=status_filter)

    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'tours/air_file_list.html', {
        'page_obj': page_obj,
        'status_filter': status_filter,
        'payment_statuses': AIRFile.PAYMENT_STATUS_CHOICES,
    })


@auth_required('tours.add_airfile')
def air_file_upload(request):
    guard = _require_tours(request)
    if guard:
        return guard
    company = request.user_company
    form = AIRFileForm(request.POST or None, request.FILES or None, company=company)

    if request.method == 'POST' and form.is_valid():
        air = form.save(commit=False)
        air.company = company
        air.uploaded_by = request.user
        air.created_by = request.user

        uploaded_file = request.FILES.get('file')
        if uploaded_file:
            if not air.original_filename:
                air.original_filename = uploaded_file.name
            air.save()
            # Auto-parse the file to prefill amounts
            from .air_parser import parse_air_file
            parsed = parse_air_file(air.file.path, air.original_filename)
            changed = []
            if parsed.billing_reference and not air.billing_reference:
                air.billing_reference = parsed.billing_reference
                changed.append('billing_reference')
            if parsed.period_from and not air.period_from:
                air.period_from = parsed.period_from
                changed.append('period_from')
            if parsed.period_to and not air.period_to:
                air.period_to = parsed.period_to
                changed.append('period_to')
            for fld in ('total_sales', 'total_refunds', 'total_commission', 'total_taxes', 'net_amount_due'):
                parsed_val = getattr(parsed, fld)
                if parsed_val and getattr(air, fld) == 0:
                    setattr(air, fld, parsed_val)
                    changed.append(fld)
            if changed:
                air.save(update_fields=changed)
            if parsed.errors:
                messages.warning(request, 'File uploaded but parser had issues: ' + '; '.join(parsed.errors))
            else:
                messages.success(request, f'AIR file "{air.original_filename}" uploaded and parsed successfully.')
        else:
            air.save()
            messages.success(request, 'AIR record saved.')
        return redirect('tours:air_file_detail', pk=air.pk)

    return render(request, 'tours/air_file_upload.html', {'form': form})


@auth_required('tours.view_airfile')
def air_file_detail(request, pk):
    guard = _require_tours(request)
    if guard:
        return guard
    from django.utils import timezone
    company = request.user_company
    air = get_object_or_404(AIRFile, pk=pk, company=company)
    payments = air.payments.filter(is_deleted=False).order_by('payment_date')
    payment_form = BSPPaymentForm()
    return render(request, 'tours/air_file_detail.html', {
        'air': air,
        'payments': payments,
        'payment_form': payment_form,
        'today': timezone.now().date(),
    })


@auth_required('tours.add_airfile')
def air_payment_add(request, pk):
    guard = _require_tours(request)
    if guard:
        return guard
    company = request.user_company
    air = get_object_or_404(AIRFile, pk=pk, company=company)

    if request.method != 'POST':
        return redirect('tours:air_file_detail', pk=pk)

    form = BSPPaymentForm(request.POST)
    if form.is_valid():
        payment = form.save(commit=False)
        payment.air_file = air
        payment.recorded_by = request.user
        payment.created_by = request.user
        payment.save()  # triggers air.recalculate_paid()
        messages.success(request, f'Payment of {payment.amount} recorded.')
    else:
        for field_errors in form.errors.values():
            for err in field_errors:
                messages.error(request, err)
    return redirect('tours:air_file_detail', pk=pk)


@auth_required('tours.change_airfile')
@require_POST
def air_payment_delete(request, pk, payment_pk):
    guard = _require_tours(request)
    if guard:
        return guard
    company = request.user_company
    air = get_object_or_404(AIRFile, pk=pk, company=company)
    payment = get_object_or_404(BSPPaymentRecord, pk=payment_pk, air_file=air)
    payment.is_deleted = True
    payment.save(update_fields=['is_deleted'])
    air.recalculate_paid()
    messages.success(request, 'Payment record removed.')
    return redirect('tours:air_file_detail', pk=pk)


@auth_required('tours.change_airfile')
@require_POST
def air_file_mark_disputed(request, pk):
    guard = _require_tours(request)
    if guard:
        return guard
    company = request.user_company
    air = get_object_or_404(AIRFile, pk=pk, company=company)
    air.payment_status = 'DISPUTED'
    air.save(update_fields=['payment_status'])
    messages.warning(request, 'AIR billing period marked as Disputed.')
    return redirect('tours:air_file_detail', pk=pk)
