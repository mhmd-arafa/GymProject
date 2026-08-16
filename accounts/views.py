from django.shortcuts import render
from django.views.generic import ListView
from .models import User
from .mixins import AdminRequiredMixin
from django.views.generic import DetailView
from django.views.generic import CreateView
from django.urls import reverse_lazy
from .forms import ClientRegisterForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.views import View
from django.views.generic import TemplateView

class ClientListView(AdminRequiredMixin, ListView):
    model = User
    template_name = "accounts/client_list.html"
    context_object_name = "clients"

    def get_queryset(self):
        return User.objects.filter(role="CLIENT")

class ClientDetailView(AdminRequiredMixin, DetailView):
    model = User
    template_name = "accounts/client_detail.html"
    context_object_name = "client"

    def get_queryset(self):
        return User.objects.filter(role="CLIENT")


class RegisterView(CreateView):
    form_class = ClientRegisterForm
    template_name = "accounts/register.html"
    success_url = reverse_lazy("login")

class DashboardRedirectView(LoginRequiredMixin, View):
    def get(self, request):
        if request.user.role == "ADMIN":
            return redirect("client-list")
        return redirect("client-home")

class ClientHomeView(LoginRequiredMixin, TemplateView):
    template_name = "accounts/client_home.html"