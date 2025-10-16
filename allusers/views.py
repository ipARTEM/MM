from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import Group
from django.urls import reverse_lazy
from django.views.generic import FormView, TemplateView
from .forms import RegisterForm
from .models import User

class RegisterView(FormView):
    template_name = "allusers/register.html"
    form_class = RegisterForm
    success_url = reverse_lazy("mm08:home")

    def form_valid(self, form):
        user: User = form.save(commit=False)
        user.role = User.Role.ANALYST        # по умолчанию — аналитик
        user.save()
        grp = Group.objects.filter(name="analysts").first()
        if grp:
            user.groups.add(grp)
        login(self.request, user)
        messages.success(self.request, "Регистрация выполнена. Добро пожаловать!")
        return super().form_valid(form)

class ProfileView(LoginRequiredMixin, TemplateView):
    template_name = "allusers/profile.html"
