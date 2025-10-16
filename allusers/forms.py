from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User

class RegisterForm(UserCreationForm):
    display_name = forms.CharField(label="Отображаемое имя", required=False)

    class Meta:
        model = User
        fields = ("username", "email", "display_name", "password1", "password2")
