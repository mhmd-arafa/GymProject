from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView
from .models import WorkoutPlan
from django.views.generic import CreateView
from django.urls import reverse_lazy
from accounts.mixins import AdminRequiredMixin
from subscriptions.mixins import ActiveSubscriptionRequiredMixin
from .forms import WorkoutPlanForm, WorkoutDayFormSet
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import UpdateView
from .models import WorkoutDay
from .forms import ExerciseFormSet

class MyWorkoutPlansView(ActiveSubscriptionRequiredMixin, ListView):
    model = WorkoutPlan
    template_name = "workouts/my_plans.html"
    context_object_name = "plans"

    def get_queryset(self):
        return WorkoutPlan.objects.filter(client=self.request.user)




class WorkoutPlanCreateView(AdminRequiredMixin, CreateView):
    model = WorkoutPlan
    form_class = WorkoutPlanForm
    template_name = "workouts/plan_form.html"
    success_url = reverse_lazy("client-list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context["days_formset"] = WorkoutDayFormSet(self.request.POST)
        else:
            context["days_formset"] = WorkoutDayFormSet()
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        days_formset = context["days_formset"]

        if days_formset.is_valid():
            self.object = form.save()
            days_formset.instance = self.object
            days_formset.save()
            return super().form_valid(form)
        else:
            return self.render_to_response(self.get_context_data(form=form))


class AddExercisesView(AdminRequiredMixin, UpdateView):
    model = WorkoutDay
    fields = []
    template_name = "workouts/add_exercises.html"

    def get_success_url(self):
        return reverse_lazy("client-list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context["exercise_formset"] = ExerciseFormSet(self.request.POST, instance=self.object)
        else:
            context["exercise_formset"] = ExerciseFormSet(instance=self.object)
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        exercise_formset = context["exercise_formset"]

        if exercise_formset.is_valid():
            self.object = form.save()
            exercise_formset.instance = self.object
            exercise_formset.save()
            return redirect(self.get_success_url())
        else:
            return self.render_to_response(self.get_context_data(form=form))