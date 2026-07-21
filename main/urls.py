from . import views
from django.urls import path
from django.conf.urls.static import static
from django.conf import settings

app_name = "main"

urlpatterns = [
    path("", views.index, name="index"),
    path("pin/", views.pin_gate, name="pin_gate"),

    path("shift/start/", views.shift_start, name="shift_start"),
    path("shift/<int:shift_id>/meter/", views.meter_entry, name="meter_entry"),
    path("shift/<int:shift_id>/receipt/", views.fuel_receipt, name="fuel_receipt"),
    path("shift/<int:shift_id>/return/", views.tank_return, name="tank_return"),
    path("shift/<int:shift_id>/close/", views.shift_close, name="shift_close"),

    path("admin-dashboard/", views.dashboard, name="dashboard"),
    path("admin-dashboard/price/", views.price_edit, name="price_edit"),
    path("admin-dashboard/reports/", views.reports, name="reports"),
    path("admin-dashboard/reports/export/", views.export_excel, name="export_excel"),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
