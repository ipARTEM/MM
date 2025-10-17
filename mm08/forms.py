from django import forms
from .models import Instrument, Candle
from .services.moex_catalog import get_moex_list, get_moex_info

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


class InstrumentCreateForm(forms.ModelForm):
    """Простая ModelForm для создания инструмента.
    Никаких внешних зависимостей/закрытых списков.
    """

    class Meta:
        model = Instrument
        fields = [
            "ticker",
            "secid",
            "shortname",
            "engine",
            "market",
            "board",
            "lot_size",
            "is_active",
        ]
        widgets = {
            "ticker": forms.TextInput(attrs={"placeholder": "Например, GAZP"}),
            "secid": forms.TextInput(attrs={"placeholder": "Можно оставить пустым"}),
            "shortname": forms.TextInput(attrs={"placeholder": "Человекопонятное имя"}),
        }

    def clean_ticker(self):
        t = (self.cleaned_data.get("ticker") or "").strip().upper()
        if not t:
            raise forms.ValidationError("Укажите тикер.")
        return t

    def save(self, user=None, commit=True):
        obj: Instrument = super().save(commit=False)
        # назначим владельца, если передали
        if user is not None and getattr(obj, "owner_id", None) is None:
            obj.owner = user
        if commit:
            obj.save()
        return obj