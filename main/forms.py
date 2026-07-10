"""
Forms for main/forms.py — Gillian Bevan Fuel Station Management System.
"""

from django import forms
from .models import Manager, Shift, FuelPrice


class PinForm(forms.Form):
    """Shared site-access PIN gate for the manager-facing tablet screens."""
    pin = forms.CharField(
        widget=forms.PasswordInput(attrs={"autofocus": True}),
        label="Site Access PIN",
    )


class ShiftStartForm(forms.Form):
    """Manager selects their name + which shift (no personal login)."""
    manager = forms.ModelChoiceField(
        queryset=Manager.objects.filter(active=True),
        label="Manager on Duty",
        empty_label="Select your name...",
    )
    shift_type = forms.ChoiceField(choices=Shift.SHIFT_TYPE_CHOICES)


class ShiftCloseForm(forms.ModelForm):
    """Manager enters the actual cash handed in at end of shift."""
    class Meta:
        model = Shift
        fields = ["cash_submitted"]
        widgets = {
            "cash_submitted": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
        }


class FuelPriceForm(forms.ModelForm):
    """Admin-only: set a new price for a product (history preserved)."""
    class Meta:
        model = FuelPrice
        fields = ["product", "price_per_litre"]
        widgets = {
            "price_per_litre": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
        }