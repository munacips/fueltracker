"""
Django models for Gillian Bevan Fuel Station Management System.
Place in stations/models.py (or split pricing-related models into a
separate `pricing` app if the project grows).
"""

from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator


# =====================================================================
# MANAGER (no login — selected from dropdown per shift)
# =====================================================================
class Manager(models.Model):
    name = models.CharField(max_length=100, unique=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


# =====================================================================
# PRODUCT (Petrol, Diesel)
# =====================================================================
class Product(models.Model):
    name = models.CharField(max_length=50, unique=True)  # 'Petrol', 'Diesel'
    unit = models.CharField(max_length=10, default="litres")

    def __str__(self):
        return self.name

    @property
    def current_price(self):
        """Returns the currently active FuelPrice for this product."""
        return (
            self.prices.filter(effective_from__lte=models.functions.Now())
            .order_by("-effective_from")
            .first()
        )


# =====================================================================
# PUMP (3 for Petrol, 2 for Diesel)
# =====================================================================
class Pump(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="pumps")
    pump_number = models.PositiveSmallIntegerField()
    label = models.CharField(max_length=50, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("product", "pump_number")
        ordering = ["product", "pump_number"]

    def __str__(self):
        return self.label or f"{self.product.name} Pump {self.pump_number}"


# =====================================================================
# FUEL PRICE (history — never overwritten, so past cash-due is locked in)
# =====================================================================
class FuelPrice(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="prices")
    price_per_litre = models.DecimalField(max_digits=10, decimal_places=2,
                                           validators=[MinValueValidator(0)])
    effective_from = models.DateTimeField(auto_now_add=True)
    set_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)  # Admin user

    class Meta:
        ordering = ["-effective_from"]

    def __str__(self):
        return f"{self.product.name} @ {self.price_per_litre} from {self.effective_from:%Y-%m-%d}"


# =====================================================================
# SHIFT (2 per day: Day / Night)
# =====================================================================
class Shift(models.Model):
    SHIFT_TYPE_CHOICES = [
        ("day", "Day Shift"),
        ("night", "Night Shift"),
    ]
    STATUS_CHOICES = [
        ("open", "Open"),
        ("closed", "Closed"),
    ]

    shift_date = models.DateField()
    shift_type = models.CharField(max_length=10, choices=SHIFT_TYPE_CHOICES)
    manager = models.ForeignKey(Manager, on_delete=models.PROTECT, related_name="shifts")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="open")

    # Manager-entered actual cash handed in for the whole shift.
    cash_submitted = models.DecimalField(max_digits=12, decimal_places=2,
                                          null=True, blank=True)

    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("shift_date", "shift_type")
        ordering = ["-shift_date", "shift_type"]

    def __str__(self):
        return f"{self.shift_date} - {self.get_shift_type_display()} ({self.manager})"

    @property
    def cash_due_total(self):
        """Sum of system-calculated cash due across all pump readings this shift."""
        return sum((r.cash_due for r in self.meter_readings.all()), start=0)

    @property
    def variance(self):
        """
        Positive = manager submitted more than expected (overage).
        Negative = manager submitted less than expected (shortfall).
        None if cash_submitted hasn't been entered yet.
        """
        if self.cash_submitted is None:
            return None
        return self.cash_submitted - self.cash_due_total


# =====================================================================
# METER READINGS (per pump, per shift)
# =====================================================================
class MeterReading(models.Model):
    shift = models.ForeignKey(Shift, on_delete=models.CASCADE, related_name="meter_readings")
    pump = models.ForeignKey(Pump, on_delete=models.PROTECT, related_name="readings")

    opening_reading = models.DecimalField(max_digits=12, decimal_places=2)
    closing_reading = models.DecimalField(max_digits=12, decimal_places=2)

    # Price locked in at time of entry — so later Admin price changes
    # never alter historical cash-due figures.
    price_snapshot = models.DecimalField(max_digits=10, decimal_places=2)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("shift", "pump")

    def __str__(self):
        return f"{self.pump} — {self.shift}"

    @property
    def litres_sold(self):
        return self.closing_reading - self.opening_reading

    @property
    def cash_due(self):
        return self.litres_sold * self.price_snapshot

    def save(self, *args, **kwargs):
        # Auto-populate opening_reading from the last closing_reading on this pump,
        # and lock in the current price, if not already set.
        if self._state.adding:
            if not self.opening_reading:
                last = (
                    MeterReading.objects.filter(pump=self.pump)
                    .order_by("-shift__shift_date", "-shift__shift_type")
                    .first()
                )
                self.opening_reading = last.closing_reading if last else 0
            if not self.price_snapshot:
                current_price = self.pump.product.current_price
                self.price_snapshot = current_price.price_per_litre if current_price else 0
        super().save(*args, **kwargs)


# =====================================================================
# FUEL RECEIVED (deliveries into tank)
# =====================================================================
class FuelReceipt(models.Model):
    shift = models.ForeignKey(Shift, on_delete=models.CASCADE, related_name="fuel_receipts")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    litres_received = models.DecimalField(max_digits=12, decimal_places=2,
                                           validators=[MinValueValidator(0)])
    supplier = models.CharField(max_length=150, blank=True)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.product} +{self.litres_received}L — {self.shift}"


# =====================================================================
# RETURN-TO-TANK (pump malfunction, fuel pumped back)
# =====================================================================
class TankReturn(models.Model):
    shift = models.ForeignKey(Shift, on_delete=models.CASCADE, related_name="tank_returns")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    pump = models.ForeignKey(Pump, on_delete=models.SET_NULL, null=True, blank=True)
    litres_returned = models.DecimalField(max_digits=12, decimal_places=2,
                                           validators=[MinValueValidator(0)])
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.product} return {self.litres_returned}L — {self.shift}"


# =====================================================================
# TANK SNAPSHOT (opening/closing tank balance per product, per shift)
# =====================================================================
class TankSnapshot(models.Model):
    shift = models.ForeignKey(Shift, on_delete=models.CASCADE, related_name="tank_snapshots")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)

    opening_balance = models.DecimalField(max_digits=14, decimal_places=2)
    fuel_received = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    fuel_returned = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    fuel_sold = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        unique_together = ("shift", "product")

    def __str__(self):
        return f"{self.product} snapshot — {self.shift}"

    @property
    def closing_balance(self):
        return self.opening_balance + self.fuel_received + self.fuel_returned - self.fuel_sold


# =====================================================================
# AUDIT LOG (price changes, edits)
# =====================================================================
class AuditLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=100)
    table_name = models.CharField(max_length=100, blank=True)
    record_id = models.PositiveIntegerField(null=True, blank=True)
    old_value = models.JSONField(null=True, blank=True)
    new_value = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.action} by {self.user} at {self.created_at:%Y-%m-%d %H:%M}"