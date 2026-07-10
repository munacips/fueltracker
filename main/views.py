"""
main/views.py — Gillian Bevan Fuel Station Management System.

Manager-facing views (shift_start, meter_entry, fuel_receipt, tank_return,
shift_close) sit behind the shared-PIN gate (@pin_required) — no personal
login required, since managers just select their name from a dropdown.

Admin-facing views (dashboard, price_edit, reports, export_excel) require
a normal Django login (@login_required), since price changes and financial
oversight need real access control.
"""

import decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from .models import (
    Manager, Product, Pump, FuelPrice, Shift,
    MeterReading, FuelReceipt, TankReturn, TankSnapshot,
)
from .forms import PinForm, ShiftStartForm, ShiftCloseForm, FuelPriceForm
from .permissions import pin_required
from .exports import export_shift_report


# =====================================================================
# PUBLIC / ENTRY
# =====================================================================
def index(request):
    """Landing page — shows the currently open shift (if any) or a
    link to start one. Redirects to the PIN gate if not yet unlocked."""
    if not request.session.get("site_access_granted"):
        return redirect("main:pin_gate")

    open_shift = Shift.objects.filter(status="open").order_by("-opened_at").first()
    return render(request, "main/index.html", {"open_shift": open_shift})


def pin_gate(request):
    """Shared site-access PIN — unlocks the manager-facing tablet screens
    for this browser session. Not tied to any individual manager."""
    if request.method == "POST":
        form = PinForm(request.POST)
        if form.is_valid():
            from django.conf import settings
            if form.cleaned_data["pin"] == settings.SITE_ACCESS_PIN:
                request.session["site_access_granted"] = True
                return redirect("main:index")
            messages.error(request, "Incorrect PIN. Please try again.")
    else:
        form = PinForm()
    return render(request, "main/pin_gate.html", {"form": form})


# =====================================================================
# MANAGER VIEWS (shared-PIN gate, no personal login)
# =====================================================================
@pin_required
def shift_start(request):
    """Manager selects their name + shift type (Day/Night) to open
    today's shift, or resumes it if already open."""
    today = timezone.localdate()

    if request.method == "POST":
        form = ShiftStartForm(request.POST)
        if form.is_valid():
            manager = form.cleaned_data["manager"]
            shift_type = form.cleaned_data["shift_type"]

            shift, created = Shift.objects.get_or_create(
                shift_date=today,
                shift_type=shift_type,
                defaults={"manager": manager},
            )
            if not created and shift.status == "closed":
                messages.error(
                    request,
                    f"The {shift.get_shift_type_display()} for {today} has "
                    "already been closed.",
                )
                return redirect("main:shift_start")

            return redirect("main:meter_entry", shift_id=shift.id)
    else:
        form = ShiftStartForm()

    return render(request, "main/manager/shift_start.html", {
        "form": form,
        "today": today,
    })


@pin_required
def meter_entry(request, shift_id):
    """Manager enters the closing meter reading for each active pump.
    Opening reading and current price are pulled in automatically —
    the manager never has to calculate anything."""
    shift = get_object_or_404(Shift, pk=shift_id, status="open")
    pumps = Pump.objects.filter(active=True).select_related("product")

    if request.method == "POST":
        has_errors = False
        for pump in pumps:
            raw_value = request.POST.get(f"closing_{pump.id}", "").strip()
            if not raw_value:
                messages.error(request, f"Missing closing reading for {pump}.")
                has_errors = True
                continue
            try:
                closing_value = decimal.Decimal(raw_value)
            except decimal.InvalidOperation:
                messages.error(request, f"Invalid number for {pump}.")
                has_errors = True
                continue

            opening_value = _get_opening_reading(pump)
            if closing_value < opening_value:
                messages.error(
                    request,
                    f"{pump}: closing reading ({closing_value}) can't be "
                    f"lower than opening reading ({opening_value})."
                )
                has_errors = True
                continue

            price = pump.product.current_price
            price_value = price.price_per_litre if price else decimal.Decimal("0")

            MeterReading.objects.update_or_create(
                shift=shift,
                pump=pump,
                defaults={
                    "opening_reading": opening_value,
                    "closing_reading": closing_value,
                    "price_snapshot": price_value,
                },
            )

        if not has_errors:
            messages.success(request, "Meter readings saved.")
            return redirect("main:fuel_receipt", shift_id=shift.id)

    pump_rows = []
    for pump in pumps:
        existing = MeterReading.objects.filter(shift=shift, pump=pump).first()
        pump_rows.append({
            "pump": pump,
            "opening_reading": _get_opening_reading(pump),
            "existing_closing": existing.closing_reading if existing else "",
        })

    return render(request, "main/manager/meter_entry.html", {
        "shift": shift,
        "pump_rows": pump_rows,
    })


@pin_required
def fuel_receipt(request, shift_id):
    """Manager logs litres of fuel received into the tank, per product
    (e.g. when a supplier delivery arrives). Optional — can be skipped
    if nothing was delivered this shift."""
    shift = get_object_or_404(Shift, pk=shift_id, status="open")
    products = Product.objects.all()

    if request.method == "POST":
        for product in products:
            raw_value = request.POST.get(f"received_{product.id}", "").strip()
            if not raw_value:
                continue
            try:
                litres_value = decimal.Decimal(raw_value)
            except decimal.InvalidOperation:
                messages.error(request, f"Invalid amount for {product}.")
                continue
            if litres_value <= 0:
                continue

            FuelReceipt.objects.create(
                shift=shift,
                product=product,
                litres_received=litres_value,
                supplier=request.POST.get(f"supplier_{product.id}", "").strip(),
                note=request.POST.get(f"note_{product.id}", "").strip(),
            )

        messages.success(request, "Fuel receipts recorded.")
        return redirect("main:tank_return", shift_id=shift.id)

    existing_receipts = FuelReceipt.objects.filter(shift=shift)
    return render(request, "main/manager/fuel_receipt.html", {
        "shift": shift,
        "products": products,
        "existing_receipts": existing_receipts,
    })


@pin_required
def tank_return(request, shift_id):
    """Manager logs any fuel pumped back into the tank after a pump
    malfunction. This adds back to tank stock but does NOT reverse the
    meter-reading 'sold' calculation from Section 3.1/3.3 of the spec."""
    shift = get_object_or_404(Shift, pk=shift_id, status="open")
    products = Product.objects.all()
    pumps = Pump.objects.filter(active=True)

    if request.method == "POST":
        for product in products:
            raw_value = request.POST.get(f"returned_{product.id}", "").strip()
            if not raw_value:
                continue
            try:
                litres_value = decimal.Decimal(raw_value)
            except decimal.InvalidOperation:
                messages.error(request, f"Invalid amount for {product}.")
                continue
            if litres_value <= 0:
                continue

            pump_id = request.POST.get(f"pump_{product.id}") or None

            TankReturn.objects.create(
                shift=shift,
                product=product,
                pump_id=pump_id,
                litres_returned=litres_value,
                note=request.POST.get(f"note_{product.id}", "").strip(),
            )

        messages.success(request, "Tank returns recorded.")
        return redirect("main:shift_close", shift_id=shift.id)

    existing_returns = TankReturn.objects.filter(shift=shift)
    return render(request, "main/manager/tank_return.html", {
        "shift": shift,
        "products": products,
        "pumps": pumps,
        "existing_returns": existing_returns,
    })


@pin_required
def shift_close(request, shift_id):
    """Manager enters the actual cash submitted for the shift. System
    compares this against the calculated cash due and shows the
    variance, then finalizes the tank stock snapshot for each product."""
    shift = get_object_or_404(Shift, pk=shift_id, status="open")

    if request.method == "POST":
        form = ShiftCloseForm(request.POST, instance=shift)
        if form.is_valid():
            shift = form.save(commit=False)
            shift.status = "closed"
            shift.closed_at = timezone.now()
            shift.save()

            _create_tank_snapshots(shift)

            variance = shift.variance
            if variance is not None and variance != 0:
                messages.warning(
                    request,
                    f"Shift closed. Cash variance: {variance:+.2f} "
                    f"({'over' if variance > 0 else 'short'})."
                )
            else:
                messages.success(request, "Shift closed. Cash reconciled exactly.")
            return redirect("main:index")
    else:
        form = ShiftCloseForm(instance=shift)

    return render(request, "main/manager/shift_close.html", {
        "shift": shift,
        "form": form,
        "cash_due_total": shift.cash_due_total,
    })


# =====================================================================
# ADMIN VIEWS (login_required)
# =====================================================================
@login_required
def dashboard(request):
    """Admin overview: current tank stock and price per product, plus
    recent shift history with cash variances."""
    stock_data = []
    for product in Product.objects.all():
        latest_snapshot = (
            TankSnapshot.objects
            .filter(product=product)
            .order_by("-shift__shift_date", "-shift__shift_type")
            .first()
        )
        current_price = product.current_price
        stock_data.append({
            "product": product,
            "tank_balance": latest_snapshot.closing_balance if latest_snapshot else None,
            "price": current_price.price_per_litre if current_price else None,
        })

    recent_shifts = (
        Shift.objects.filter(status="closed")
        .select_related("manager")
        .order_by("-shift_date", "-shift_type")[:14]
    )

    return render(request, "main/admin/dashboard.html", {
        "stock_data": stock_data,
        "recent_shifts": recent_shifts,
    })


@login_required
def price_edit(request):
    """Admin sets a new selling price per litre for a product. Old
    prices are preserved (FuelPrice history), so past cash-due figures
    never change retroactively."""
    if request.method == "POST":
        form = FuelPriceForm(request.POST)
        if form.is_valid():
            price = form.save(commit=False)
            price.set_by = request.user
            price.save()
            messages.success(
                request,
                f"{price.product} price updated to {price.price_per_litre} "
                "per litre. This applies to all new sales going forward."
            )
            return redirect("main:price_edit")
    else:
        form = FuelPriceForm()

    price_history = FuelPrice.objects.select_related("product", "set_by").order_by("-effective_from")[:20]
    return render(request, "main/admin/price_edit.html", {
        "form": form,
        "price_history": price_history,
    })


@login_required
def reports(request):
    """Admin views sales/cash summary over a selected date range."""
    date_from = request.GET.get("from")
    date_to = request.GET.get("to")

    shifts = Shift.objects.filter(status="closed").select_related("manager")
    if date_from:
        shifts = shifts.filter(shift_date__gte=date_from)
    if date_to:
        shifts = shifts.filter(shift_date__lte=date_to)
    shifts = shifts.order_by("-shift_date", "shift_type")

    paginator = Paginator(shifts, 30)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "main/admin/reports.html", {
        "page_obj": page_obj,
        "date_from": date_from or "",
        "date_to": date_to or "",
    })


@login_required
def export_excel(request):
    """Admin downloads an .xlsx report for the selected date range."""
    date_from = request.GET.get("from")
    date_to = request.GET.get("to")

    workbook = export_shift_report(date_from, date_to)
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = 'attachment; filename="fuel_station_report.xlsx"'
    workbook.save(response)
    return response


# =====================================================================
# INTERNAL HELPERS
# =====================================================================
def _get_opening_reading(pump):
    """Returns the last recorded closing_reading for a pump (i.e. this
    shift's opening reading), or 0 if the pump has no history yet."""
    last_reading = (
        MeterReading.objects
        .filter(pump=pump)
        .order_by("-shift__shift_date", "-shift__shift_type", "-created_at")
        .first()
    )
    return last_reading.closing_reading if last_reading else decimal.Decimal("0")


def _create_tank_snapshots(shift):
    """Builds the end-of-shift TankSnapshot row for each product:
    opening balance carried from the last snapshot, plus fuel received
    and returned this shift, minus fuel sold (from meter readings)."""
    for product in Product.objects.all():
        previous_snapshot = (
            TankSnapshot.objects
            .filter(product=product)
            .exclude(shift=shift)
            .order_by("-shift__shift_date", "-shift__shift_type")
            .first()
        )
        opening_balance = previous_snapshot.closing_balance if previous_snapshot else decimal.Decimal("0")

        fuel_received = FuelReceipt.objects.filter(
            shift=shift, product=product
        ).values_list("litres_received", flat=True)
        fuel_received_total = sum(fuel_received, decimal.Decimal("0"))

        fuel_returned = TankReturn.objects.filter(
            shift=shift, product=product
        ).values_list("litres_returned", flat=True)
        fuel_returned_total = sum(fuel_returned, decimal.Decimal("0"))

        fuel_sold_total = decimal.Decimal("0")
        for reading in MeterReading.objects.filter(shift=shift, pump__product=product):
            fuel_sold_total += reading.litres_sold

        TankSnapshot.objects.update_or_create(
            shift=shift,
            product=product,
            defaults={
                "opening_balance": opening_balance,
                "fuel_received": fuel_received_total,
                "fuel_returned": fuel_returned_total,
                "fuel_sold": fuel_sold_total,
            },
        )