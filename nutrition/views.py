from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext as _
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from accounts.mixins import AdminRequiredMixin

from .forms import (
    FoodItemForm,
    MacroTargetForm,
    MealFoodItemFormSet,
    MealFormSet,
    NutritionPlanForm,
    SupplementScheduleFormSet,
)
from .models import FoodItem, MacroTarget, Meal, NutritionPlan


class MyNutritionPlansView(LoginRequiredMixin, ListView):
    model = NutritionPlan
    template_name = "nutrition/my_nutrition.html"
    context_object_name = "plans"

    def get_queryset(self):
        return NutritionPlan.objects.filter(
            client=self.request.user
        ).prefetch_related("meals__alternatives", "meals__food_items__food",
                           "supplement_schedule__supplement")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Pair each plan with its target comparison so the client can see whether
        # the plan actually hits the numbers they were given.
        context["plan_rows"] = [
            {
                "plan": plan,
                "totals": plan.daily_totals(),
                "comparison": plan.target_comparison(),
                "meals": plan.meals.filter(alternative_of__isnull=True),
            }
            for plan in context["plans"]
        ]
        return context


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


class NutritionPlanDetailView(AdminRequiredMixin, DetailView):
    model = NutritionPlan
    template_name = "nutrition/plan_detail.html"
    context_object_name = "plan"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["totals"] = self.object.daily_totals()
        context["comparison"] = self.object.target_comparison()
        context["meals"] = self.object.meals.filter(
            alternative_of__isnull=True
        ).prefetch_related("alternatives", "food_items__food")
        return context


class MealFoodItemsView(AdminRequiredMixin, UpdateView):
    """Build a meal from weighed foods; macros compute from the food database."""

    model = Meal
    fields = []
    template_name = "nutrition/meal_food_items.html"

    def get_success_url(self):
        return reverse("nutrition-plan-detail", args=[self.object.plan_id])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context["items_formset"] = MealFoodItemFormSet(
                self.request.POST, instance=self.object
            )
        else:
            context["items_formset"] = MealFoodItemFormSet(instance=self.object)
        context["meal"] = self.object
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        items_formset = context["items_formset"]
        if not items_formset.is_valid():
            return self.render_to_response(self.get_context_data(form=form))

        self.object = form.save()
        items_formset.instance = self.object
        items_formset.save()

        # Recompute stored macros from the weighed foods. This is the "trainer
        # enters 150g grilled chicken and macros compute automatically" step.
        if self.object.recalculate_totals():
            messages.success(
                self.request,
                _("Macros recalculated: %(calories)s kcal.")
                % {"calories": self.object.calories},
            )
        return redirect(self.get_success_url())


class MacroTargetUpdateView(AdminRequiredMixin, UpdateView):
    model = MacroTarget
    form_class = MacroTargetForm
    template_name = "nutrition/macro_target_form.html"

    def get_object(self, queryset=None):
        plan = get_object_or_404(NutritionPlan, pk=self.kwargs["plan_pk"])
        target, _created = MacroTarget.objects.get_or_create(
            plan=plan,
            defaults={
                "target_calories": 2000,
                "target_protein": 150,
                "target_carbs": 200,
                "target_fats": 60,
            },
        )
        return target

    def get_success_url(self):
        return reverse("nutrition-plan-detail", args=[self.object.plan_id])


class SupplementScheduleView(AdminRequiredMixin, UpdateView):
    model = NutritionPlan
    fields = []
    template_name = "nutrition/supplement_schedule.html"

    def get_success_url(self):
        return reverse("nutrition-plan-detail", args=[self.object.pk])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context["schedule_formset"] = SupplementScheduleFormSet(
                self.request.POST, instance=self.object
            )
        else:
            context["schedule_formset"] = SupplementScheduleFormSet(instance=self.object)
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        schedule_formset = context["schedule_formset"]
        if not schedule_formset.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        self.object = form.save()
        schedule_formset.instance = self.object
        schedule_formset.save()
        return redirect(self.get_success_url())


class FoodItemListView(AdminRequiredMixin, ListView):
    model = FoodItem
    template_name = "nutrition/food_list.html"
    context_object_name = "foods"

    def get_queryset(self):
        queryset = FoodItem.objects.all()
        search = self.request.GET.get("q")
        if search:
            queryset = queryset.filter(name__icontains=search)
        if self.request.GET.get("egyptian"):
            queryset = queryset.filter(is_egyptian_staple=True)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["search"] = self.request.GET.get("q", "")
        context["egyptian_only"] = bool(self.request.GET.get("egyptian"))
        return context


class FoodItemCreateView(AdminRequiredMixin, CreateView):
    model = FoodItem
    form_class = FoodItemForm
    template_name = "nutrition/food_form.html"
    success_url = reverse_lazy("food-list")


class NutritionPlanPrintView(LoginRequiredMixin, DetailView):
    """Print-optimised plan. Save-as-PDF from the browser keeps Arabic shaping."""

    model = NutritionPlan
    template_name = "nutrition/plan_print.html"
    context_object_name = "plan"

    def get_queryset(self):
        queryset = NutritionPlan.objects.select_related("client")
        # A client may print only their own plan; the trainer may print any.
        if self.request.user.role != "ADMIN":
            queryset = queryset.filter(client=self.request.user)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["totals"] = self.object.daily_totals()
        context["comparison"] = self.object.target_comparison()
        context["meals"] = self.object.meals.filter(
            alternative_of__isnull=True
        ).prefetch_related("alternatives", "food_items__food")
        return context
