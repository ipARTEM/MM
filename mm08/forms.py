from django import forms
from .models import Instrument, Candle

class InstrumentForm(forms.ModelForm):
    """Форма добавления/редактирования инструмента (связана с моделью)."""
    class Meta:
        model = Instrument
        fields = ["ticker", "secid", "shortname", "engine", "market", "board", "lot_size", "is_active"]
        widgets = {
            "ticker": forms.TextInput(attrs={"class": "mm-input", "placeholder": "SiM5"}),
            "secid": forms.TextInput(attrs={"class": "mm-input", "placeholder": "SECID (опц.)"}),
            "shortname": forms.TextInput(attrs={"class": "mm-input", "placeholder": "Фьючерс USDRUB"}),
            "engine": forms.TextInput(attrs={"class": "mm-input", "placeholder": "stock / futures"}),
            "market": forms.TextInput(attrs={"class": "mm-input", "placeholder": "shares / futures / index"}),
            "board": forms.TextInput(attrs={"class": "mm-input", "placeholder": "TQBR / RFUD"}),
            "lot_size": forms.NumberInput(attrs={"class": "mm-input", "min": 1}),
        }

class CandleFilterForm(forms.Form):
    """Независимая форма (не связана с моделью) — выбор инструмента и интервала."""
    instrument = forms.ModelChoiceField(
        queryset=Instrument.objects.filter(is_active=True).order_by("ticker"),
        label="Инструмент"
    )
    interval = forms.ChoiceField(
        choices=Candle.Interval.choices,
        label="Интервал"
    )
