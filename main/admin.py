from django.contrib import admin

from .models import (
    AuditLog,
    FuelPrice,
    FuelReceipt,
    Manager,
    MeterReading,
    Product,
    Pump,
    Shift,
    TankReturn,
    TankSnapshot,
)


@admin.register(Manager)
class ManagerAdmin(admin.ModelAdmin):
    list_display = ("name", "active", "created_at")
    list_filter = ("active",)
    search_fields = ("name",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "unit")
    search_fields = ("name",)


@admin.register(Pump)
class PumpAdmin(admin.ModelAdmin):
    list_display = ("pump_number", "product", "label", "active")
    list_filter = ("product", "active")
    search_fields = ("label", "product__name")


@admin.register(FuelPrice)
class FuelPriceAdmin(admin.ModelAdmin):
    list_display = ("product", "price_per_litre", "effective_from", "set_by")
    list_filter = ("product", "effective_from")
    search_fields = ("product__name", "set_by__username")
    autocomplete_fields = ("product", "set_by")


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = (
        "shift_date",
        "shift_type",
        "manager",
        "status",
        "cash_submitted",
        "opened_at",
        "closed_at",
    )
    list_filter = ("shift_type", "status", "manager", "shift_date")
    search_fields = ("manager__name",)
    autocomplete_fields = ("manager",)


@admin.register(MeterReading)
class MeterReadingAdmin(admin.ModelAdmin):
    list_display = (
        "shift",
        "pump",
        "opening_reading",
        "closing_reading",
        "price_snapshot",
        "created_at",
    )
    list_filter = ("pump__product", "pump", "shift__shift_type")
    search_fields = ("pump__label", "pump__product__name",
                     "shift__manager__name")
    autocomplete_fields = ("shift", "pump")


@admin.register(FuelReceipt)
class FuelReceiptAdmin(admin.ModelAdmin):
    list_display = ("shift", "product", "litres_received",
                    "supplier", "created_at")
    list_filter = ("product", "supplier", "created_at")
    search_fields = ("supplier", "note", "product__name",
                     "shift__manager__name")
    autocomplete_fields = ("shift", "product")


@admin.register(TankReturn)
class TankReturnAdmin(admin.ModelAdmin):
    list_display = ("shift", "product", "pump",
                    "litres_returned", "created_at")
    list_filter = ("product", "pump", "created_at")
    search_fields = ("note", "product__name",
                     "pump__label", "shift__manager__name")
    autocomplete_fields = ("shift", "product", "pump")


@admin.register(TankSnapshot)
class TankSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "shift",
        "product",
        "opening_balance",
        "fuel_received",
        "fuel_returned",
        "fuel_sold",
        "closing_balance",
    )
    list_filter = ("product",)
    search_fields = ("product__name", "shift__manager__name")
    autocomplete_fields = ("shift", "product")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("action", "user", "table_name", "record_id", "created_at")
    list_filter = ("action", "table_name", "created_at")
    search_fields = ("action", "table_name", "user__username")
    readonly_fields = (
        "user",
        "action",
        "table_name",
        "record_id",
        "old_value",
        "new_value",
        "created_at",
    )
