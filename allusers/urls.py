from django.urls import path
from django.contrib.auth import views as auth_views
from .views import RegisterView, ProfileView

app_name = "allusers"

urlpatterns = [
    path("login/",  auth_views.LoginView.as_view(template_name="allusers/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(next_page="mm08:home"), name="logout"),
    path("register/", RegisterView.as_view(), name="register"),
    path("profile/",  ProfileView.as_view(),  name="profile"),
]
