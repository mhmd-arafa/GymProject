from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, CreateView
from django.urls import reverse_lazy
from accounts.mixins import AdminRequiredMixin
from subscriptions.mixins import ActiveSubscriptionRequiredMixin
from .models import NutritionPlan
from .forms import NutritionPlanForm, MealFormSet


class MyNutritionPlansView(ActiveSubscriptionRequiredMixin, ListView):
    model = NutritionPlan
    template_name = "nutrition/my_nutrition.html"
    context_object_name = "plans"

    def get_queryset(self):
        return NutritionPlan.objects.filter(client=self.request.user)


class NutritionPlanCreateView(AdminRequiredMixin, CreateView):
    model = NutritionPlan
    form_class = NutritionPlanForm
    template_name = "nutrition/plan_form.html"
    success_url = reverse_lazy("client-list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context["meals_formset"] = MealFormSet(self.request.POST)
        else:
            context["meals_formset"] = MealFormSet()
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        meals_formset = context["meals_formset"]

        if meals_formset.is_valid():
            self.object = form.save()
            meals_formset.instance = self.object
            meals_formset.save()
            return super().form_valid(form)
        else:
            return self.render_to_response(self.get_context_data(form=form))
