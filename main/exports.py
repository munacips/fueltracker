"""
main/exports.py — Excel report generation using openpyxl.
"""

from openpyxl import Workbook
from openpyxl.styles import Font

from .models import Shift


def export_shift_report(date_from=None, date_to=None):
    """
    Builds an .xlsx Workbook summarizing closed shifts (one row per shift)
    between date_from and date_to (inclusive). Dates as 'YYYY-MM-DD' strings
    or None to leave that bound open.
    """
    shifts = Shift.objects.filter(status="closed").order_by("shift_date", "shift_type")
    if date_from:
        shifts = shifts.filter(shift_date__gte=date_from)
    if date_to:
        shifts = shifts.filter(shift_date__lte=date_to)

    wb = Workbook()
    ws = wb.active
    ws.title = "Shift Summary"

    headers = [
        "Date", "Shift", "Manager", "Cash Due (System)",
        "Cash Submitted", "Variance", "Status",
    ]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    for shift in shifts:
        ws.append([
            shift.shift_date.isoformat(),
            shift.get_shift_type_display(),
            shift.manager.name,
            float(shift.cash_due_total),
            float(shift.cash_submitted) if shift.cash_submitted is not None else None,
            float(shift.variance) if shift.variance is not None else None,
            shift.status,
        ])

    # Auto-size columns roughly
    for col_cells in ws.columns:
        length = max(len(str(c.value)) if c.value is not None else 0 for c in col_cells)
        ws.column_dimensions[col_cells[0].column_letter].width = length + 2

    return wb