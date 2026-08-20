from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Prefetch
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from accounts.mixins import AdminRequiredMixin
from accounts.models import User

from . import services
from .forms import (
    ExerciseFormSet,
    SetLogForm,
    SessionCompleteForm,
    WorkoutDayFormSet,
    WorkoutPlanForm,
    WorkoutTemplateForm,
)
from .models import (
    Exercise,
    ExerciseCatalog,
    SetLog,
    WorkoutDay,
    WorkoutPlan,
    WorkoutSession,
)


class MyWorkoutPlansView(ActiveSubscriptionRequiredMixin, ListView):
    model = WorkoutPlan
    template_name = "workouts/my_plans.html"
    context_object_name = "plans"

    def get_queryset(self):
        # is_template plans have client=None, so they can never appear here.
        return (
            WorkoutPlan.objects.filter(client=self.request.user, is_template=False)
            .prefetch_related(
                Prefetch(
                    "days",
                    queryset=WorkoutDay.objects.prefetch_related(
                        "exercises__catalog_exercise"
                    ),
                )
            )
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["adherence"] = services.adherence(self.request.user)
        context["active_session"] = WorkoutSession.objects.filter(
            client=self.request.user, completed_at__isnull=True
        ).first()
        return context


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
        context["catalog"] = ExerciseCatalog.objects.filter(is_active=True)
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


# --------------------------------------------------------------------------
# Exercise library
# --------------------------------------------------------------------------


class ExerciseCatalogListView(AdminRequiredMixin, ListView):
    model = ExerciseCatalog
    template_name = "workouts/exercise_catalog.html"
    context_object_name = "exercises"

    def get_queryset(self):
        queryset = ExerciseCatalog.objects.all()
        muscle_group = self.request.GET.get("muscle_group")
        if muscle_group:
            queryset = queryset.filter(muscle_group=muscle_group)
        search = self.request.GET.get("q")
        if search:
            queryset = queryset.filter(name__icontains=search)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["muscle_groups"] = ExerciseCatalog.MuscleGroup.choices
        context["selected_group"] = self.request.GET.get("muscle_group", "")
        context["search"] = self.request.GET.get("q", "")
        return context


class ExerciseCatalogCreateView(AdminRequiredMixin, CreateView):
    model = ExerciseCatalog
    template_name = "workouts/exercise_catalog_form.html"
    fields = [
        "name",
        "muscle_group",
        "equipment",
        "video_url",
        "instructions",
        "is_active",
    ]
    success_url = reverse_lazy("exercise-catalog")


# --------------------------------------------------------------------------
# Plan templates
# --------------------------------------------------------------------------


class PlanTemplateListView(AdminRequiredMixin, ListView):
    template_name = "workouts/template_list.html"
    context_object_name = "templates"

    def get_queryset(self):
        return WorkoutPlan.objects.filter(is_template=True).prefetch_related(
            "days__exercises"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["clients"] = User.objects.filter(role=User.Role.CLIENT)
        return context


class PlanTemplateCreateView(AdminRequiredMixin, CreateView):
    model = WorkoutPlan
    form_class = WorkoutTemplateForm
    template_name = "workouts/template_form.html"
    success_url = reverse_lazy("plan-template-list")

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
        if not days_formset.is_valid():
            return self.render_to_response(self.get_context_data(form=form))

        form.instance.is_template = True
        form.instance.client = None
        self.object = form.save()
        days_formset.instance = self.object
        days_formset.save()
        messages.success(
            self.request,
            _("Template “%(title)s” saved. Add exercises to each day, then clone it.")
            % {"title": self.object.title},
        )
        return HttpResponseRedirect(self.get_success_url())


class PlanCloneView(AdminRequiredMixin, View):
    """Assign a template to a client by deep-copying it. POST only."""

    def post(self, request, pk):
        template = get_object_or_404(WorkoutPlan, pk=pk, is_template=True)
        client = get_object_or_404(
            User, pk=request.POST.get("client"), role=User.Role.CLIENT
        )
        title = request.POST.get("title") or None
        new_plan = template.clone_for(client, title=title)
        messages.success(
            request,
            _("Assigned “%(title)s” to %(client)s.")
            % {"title": new_plan.title, "client": client.username},
        )
        return redirect("client-detail", pk=client.pk)


# --------------------------------------------------------------------------
# In-gym session logging
# --------------------------------------------------------------------------


class SessionStartView(LoginRequiredMixin, View):
    """Open a session for a plan day, reusing one already in progress."""

    def post(self, request, day_pk):
        day = get_object_or_404(
            WorkoutDay, pk=day_pk, plan__client=request.user, plan__is_template=False
        )
        session = WorkoutSession.objects.filter(
            client=request.user, day=day, completed_at__isnull=True
        ).first()
        if session is None:
            session = WorkoutSession.objects.create(
                client=request.user, plan=day.plan, day=day
            )
        return redirect("workout-session", pk=session.pk)


class ActiveSessionView(LoginRequiredMixin, DetailView):
    """The in-gym screen: every exercise with last time's numbers and a log form."""

    model = WorkoutSession
    template_name = "workouts/session.html"
    context_object_name = "session"

    def get_queryset(self):
        return WorkoutSession.objects.filter(client=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session = self.object
        logged = list(session.set_logs.select_related("exercise", "catalog_exercise"))

        rows = []
        exercises = (
            session.day.exercises.select_related("catalog_exercise")
            if session.day
            else Exercise.objects.none()
        )
        for exercise in exercises:
            exercise_sets = [s for s in logged if s.exercise_id == exercise.pk]
            suggestion = services.suggest_progression(self.request.user, exercise)

            # Pre-fill the weight with the most useful number available, in
            # descending order of confidence: what the rules say to lift today,
            # what the client already put on the bar this session, what the plan
            # prescribes. Saves typing the same number three times per exercise.
            if suggestion:
                suggested_weight = suggestion["suggested_weight_kg"]
            elif exercise_sets:
                suggested_weight = exercise_sets[-1].weight_kg
            else:
                suggested_weight = exercise.target_weight_kg

            rows.append(
                {
                    "exercise": exercise,
                    "sets": exercise_sets,
                    "next_set_number": len(exercise_sets) + 1,
                    "last_time": services.last_performance(
                        self.request.user,
                        exercise.catalog_exercise,
                        before_session=session,
                    ),
                    "suggestion": suggestion,
                    "suggested_weight": suggested_weight,
                }
            )

        context["rows"] = rows
        context["lifts_started"] = sum(1 for row in rows if row["sets"])
        context["complete_form"] = SessionCompleteForm(instance=session)
        return context


class LogSetView(LoginRequiredMixin, View):
    """Record one set.

    Returns an HTML fragment for HTMX so the page never reloads mid-workout, and
    falls back to a redirect for a plain form POST. The fallback matters: this is
    the one screen guaranteed to be used on unreliable gym wifi, and it keeps
    working if the HTMX script fails to load.
    """

    def post(self, request, session_pk):
        session = get_object_or_404(
            WorkoutSession, pk=session_pk, client=request.user, completed_at__isnull=True
        )
        exercise = get_object_or_404(
            Exercise, pk=request.POST.get("exercise"), day__plan__client=request.user
        )
        form = SetLogForm(request.POST)

        if not form.is_valid():
            if request.headers.get("HX-Request"):
                return render(
                    request,
                    "workouts/partials/set_form_errors.html",
                    {"form": form, "exercise": exercise, "session": session},
                    status=400,
                )
            messages.error(request, _("Could not save that set. Check the numbers."))
            return redirect("workout-session", pk=session.pk)

        set_log = form.save(commit=False)
        set_log.session = session
        set_log.exercise = exercise
        if not set_log.set_number:
            set_log.set_number = (
                session.set_logs.filter(exercise=exercise).count() + 1
            )
        set_log.save()

        records = services.detect_prs(set_log)

        if request.headers.get("HX-Request"):
            return render(
                request,
                "workouts/partials/set_row.html",
                {
                    "set_log": set_log,
                    "records": records,
                    "session": session,
                    "exercise": exercise,
                    "next_set_number": session.set_logs.filter(
                        exercise=exercise
                    ).count()
                    + 1,
                },
            )

        for record in records:
            messages.success(
                request,
                _("New best on %(exercise)s: %(type)s %(value)s 💪")
                % {
                    "exercise": record.catalog_exercise.name,
                    "type": record.get_record_type_display(),
                    "value": record.value,
                },
            )
        return redirect("workout-session", pk=session.pk)


class DeleteSetView(LoginRequiredMixin, View):
    """Undo a mistyped set."""

    def post(self, request, pk):
        set_log = get_object_or_404(SetLog, pk=pk, session__client=request.user)
        session_pk = set_log.session_id
        set_log.delete()
        if request.headers.get("HX-Request"):
            # An empty 200 lets hx-swap="outerHTML" remove the row.
            return render(request, "workouts/partials/empty.html")
        return redirect("workout-session", pk=session_pk)


class SessionCompleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        session = get_object_or_404(
            WorkoutSession, pk=pk, client=request.user, completed_at__isnull=True
        )
        form = SessionCompleteForm(request.POST, instance=session)
        if form.is_valid():
            session = form.save(commit=False)
            session.completed_at = timezone.now()
            session.save()
            messages.success(request, _("Session logged. Well done."))
        else:
            messages.error(request, _("Could not finish the session."))
        return redirect("workout-history")


class SessionHistoryView(LoginRequiredMixin, ListView):
    model = WorkoutSession
    template_name = "workouts/session_history.html"
    context_object_name = "sessions"
    paginate_by = 20

    def get_queryset(self):
        return (
            WorkoutSession.objects.filter(client=self.request.user)
            .prefetch_related("set_logs__catalog_exercise")
            .select_related("day")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["adherence"] = services.adherence(self.request.user)
        context["records"] = self.request.user.personal_records.select_related(
            "catalog_exercise"
        )
        return context


class ExerciseHistoryView(LoginRequiredMixin, DetailView):
    """Per-exercise chart and set-by-set history."""

    model = ExerciseCatalog
    template_name = "workouts/exercise_history.html"
    context_object_name = "exercise"
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def get_context_data(self, **kwargs):
        from progress.charts import build_line_chart

        context = super().get_context_data(**kwargs)
        client = self.request.user
        # A trainer can inspect any client's history via ?client=<pk>.
        if client.role == User.Role.ADMIN and self.request.GET.get("client"):
            client = get_object_or_404(
                User, pk=self.request.GET["client"], role=User.Role.CLIENT
            )

        points = services.exercise_history(client, self.object)
        context["history"] = points
        context["subject"] = client
        context["weight_chart"] = build_line_chart(
            [(p["date"], p["top_weight_kg"]) for p in points],
            label=_("Top set (kg)"),
        )
        context["volume_chart"] = build_line_chart(
            [(p["date"], p["volume_kg"]) for p in points],
            label=_("Session volume (kg)"),
        )
        context["records"] = client.personal_records.filter(
            catalog_exercise=self.object
        )
        return context


class WorkoutPlanPrintView(LoginRequiredMixin, DetailView):
    """Print-optimised plan. Save-as-PDF from the browser keeps Arabic shaping."""

    model = WorkoutPlan
    template_name = "workouts/plan_print.html"
    context_object_name = "plan"

    def get_queryset(self):
        queryset = WorkoutPlan.objects.select_related("client").prefetch_related(
            "days__exercises__catalog_exercise"
        )
        # A client may print only their own plan; the trainer may print any.
        if self.request.user.role != User.Role.ADMIN:
            queryset = queryset.filter(client=self.request.user, is_template=False)
        return queryset
