from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Exists, OuterRef
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView

from progress.models import CheckIn
from subscriptions.models import PaymentProof, Subscription
from subscriptions.services import expire_overdue_subscriptions
from workouts import services as workout_services
from workouts.models import WorkoutPlan, WorkoutSession

from .forms import ClientRegisterForm, IntakeFormForm, TrainerNoteForm, UserProfileForm
from .mixins import AdminRequiredMixin
from .models import IntakeForm, User

#: A subscription inside this many days needs a renewal conversation.
EXPIRING_SOON_DAYS = 7

#: No logged session in this long means the client has gone quiet.
INACTIVE_DAYS = 10


class ClientListView(AdminRequiredMixin, ListView):
    model = User
    template_name = "accounts/client_list.html"
    context_object_name = "clients"

    def get_queryset(self):
        return User.objects.filter(role=User.Role.CLIENT).annotate(
            plan_count=Count("workout_plans", distinct=True),
            session_count=Count("workout_sessions", distinct=True),
        )


class ClientDetailView(AdminRequiredMixin, DetailView):
    model = User
    template_name = "accounts/client_detail.html"
    context_object_name = "client"

    def get_queryset(self):
        return User.objects.filter(role=User.Role.CLIENT)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        client = self.object

        context["workout_plans"] = client.workout_plans.filter(
            is_template=False
        ).prefetch_related("days__exercises")
        context["nutrition_plans"] = client.nutrition_plans.prefetch_related("meals")
        context["subscription"] = (
            client.subscriptions.select_related("plan").order_by("-created_at").first()
        )
        context["recent_sessions"] = client.workout_sessions.all()[:5]
        context["adherence"] = workout_services.adherence(client)
        context["records"] = client.personal_records.select_related("catalog_exercise")
        context["checkins"] = client.checkins.all()[:5]
        context["intake"] = getattr(client, "intake", None)

        # Private notes: rendered only in this admin-only template.
        context["notes"] = client.trainer_notes.select_related("author")
        context["note_form"] = TrainerNoteForm()

        # Progression suggestions across the client's most recent plan.
        latest_plan = context["workout_plans"].first()
        context["suggestions"] = (
            workout_services.plan_progression_suggestions(client, latest_plan)
            if latest_plan
            else []
        )
        return context


class TrainerNoteCreateView(AdminRequiredMixin, View):
    """Add a private note. Never exposed on any client-facing view."""

    def post(self, request, pk):
        form = TrainerNoteForm(request.POST)
        if form.is_valid():
            note = form.save(commit=False)
            note.client_id = pk
            note.author = request.user
            note.save()
            messages.success(request, _("Note saved. Only you can see it."))
        else:
            messages.error(request, _("Could not save the note."))
        return redirect("client-detail", pk=pk)


class TrainerDashboardView(AdminRequiredMixin, TemplateView):
    """The attention queue: who needs the trainer today, not just a client list."""

    template_name = "accounts/trainer_dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Keep statuses honest before reading them.
        expire_overdue_subscriptions()

        today = timezone.localdate()
        clients = User.objects.filter(role=User.Role.CLIENT)

        context["client_count"] = clients.count()

        context["expiring_soon"] = (
            Subscription.objects.filter(
                status=Subscription.Status.ACTIVE,
                end_date__gte=today,
                end_date__lte=today + timedelta(days=EXPIRING_SOON_DAYS),
            )
            .select_related("client", "plan")
            .order_by("end_date")
        )

        assigned_plan = WorkoutPlan.objects.filter(
            client=OuterRef("pk"), is_template=False
        )
        context["without_plan"] = clients.filter(~Exists(assigned_plan))

        context["inactive_clients"] = workout_services.clients_without_recent_session(
            list(clients), days=INACTIVE_DAYS
        )

        context["unreviewed_checkins"] = (
            CheckIn.objects.filter(submitted_at__isnull=False, reviewed=False)
            .select_related("client")
            .order_by("submitted_at")
        )

        context["overdue_checkins"] = (
            CheckIn.objects.filter(submitted_at__isnull=True, due_date__lt=today)
            .select_related("client")
            .order_by("due_date")
        )

        context["pending_payments"] = (
            PaymentProof.objects.filter(status=PaymentProof.Status.PENDING)
            .select_related("subscription__client", "subscription__plan")
            .order_by("submitted_at")
        )

        intake = IntakeForm.objects.filter(client=OuterRef("pk"))
        context["without_intake"] = clients.filter(~Exists(intake))

        context["expiring_soon_days"] = EXPIRING_SOON_DAYS
        context["inactive_days"] = INACTIVE_DAYS

        # Drives the header count and the "nothing waiting" state. Counting here
        # rather than in the template keeps the two from ever disagreeing.
        context["setup_total"] = (
            context["without_plan"].count() + context["without_intake"].count()
        )
        context["attention_total"] = (
            context["pending_payments"].count()
            + context["unreviewed_checkins"].count()
            + context["expiring_soon"].count()
            + context["overdue_checkins"].count()
            + len(context["inactive_clients"])
            + context["setup_total"]
        )
        return context


class RegisterView(CreateView):
    form_class = ClientRegisterForm
    template_name = "accounts/register.html"
    success_url = reverse_lazy("login")


class IntakeFormView(LoginRequiredMixin, CreateView):
    """Questionnaire that replaces the WhatsApp back-and-forth before a plan."""

    model = IntakeForm
    form_class = IntakeFormForm
    template_name = "accounts/intake_form.html"
    success_url = reverse_lazy("client-home")

    def dispatch(self, request, *args, **kwargs):
        # One per client: send repeat visits to the edit view instead.
        if request.user.is_authenticated and hasattr(request.user, "intake"):
            return redirect("intake-edit")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.client = self.request.user
        messages.success(self.request, _("Thanks — your coach has what they need."))
        return super().form_valid(form)


class IntakeFormUpdateView(LoginRequiredMixin, UpdateView):
    model = IntakeForm
    form_class = IntakeFormForm
    template_name = "accounts/intake_form.html"
    success_url = reverse_lazy("client-home")

    def get_object(self, queryset=None):
        return self.request.user.intake


class ProfileUpdateView(LoginRequiredMixin, UpdateView):
    """Phone number and language preference."""

    model = User
    form_class = UserProfileForm
    template_name = "accounts/profile_form.html"
    success_url = reverse_lazy("client-home")

    def get_object(self, queryset=None):
        return self.request.user

    def form_valid(self, form):
        from django.conf import settings

        response = super().form_valid(form)
        # Mirror the saved preference into the language cookie so it takes effect
        # immediately, matching what set_language would have done.
        response.set_cookie(settings.LANGUAGE_COOKIE_NAME, self.object.language)
        messages.success(self.request, _("Profile updated."))
        return response


class DashboardRedirectView(LoginRequiredMixin, View):
    def get(self, request):
        if request.user.role == User.Role.ADMIN:
            return redirect("trainer-dashboard")
        return redirect("client-home")


class ClientHomeView(LoginRequiredMixin, TemplateView):
    template_name = "accounts/client_home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        context["active_session"] = WorkoutSession.objects.filter(
            client=user, completed_at__isnull=True
        ).first()
        context["workout_plan"] = (
            user.workout_plans.filter(is_template=False)
            .prefetch_related("days__exercises")
            .first()
        )
        context["nutrition_plan"] = user.nutrition_plans.first()
        context["subscription"] = (
            user.subscriptions.select_related("plan").order_by("-created_at").first()
        )
        context["due_checkin"] = (
            user.checkins.filter(submitted_at__isnull=True).order_by("due_date").first()
        )
        context["adherence"] = workout_services.adherence(user)
        context["needs_intake"] = not hasattr(user, "intake")
        context["recent_records"] = user.personal_records.select_related(
            "catalog_exercise"
        )[:5]
        return context
