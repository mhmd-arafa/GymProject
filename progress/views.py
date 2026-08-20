from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    TemplateView,
    UpdateView,
)

from accounts.mixins import AdminRequiredMixin
from accounts.models import User
from workouts import services as workout_services

from .charts import measurement_chart
from .forms import (
    POSE_SLOTS,
    BodyMeasurementForm,
    CheckInReplyForm,
    CheckInScheduleForm,
    CheckInSubmitForm,
    ProgressPhotoForm,
)
from .models import BodyMeasurement, CheckIn, ProgressPhoto


def photo_timeline(photos):
    """Group photos by pose, newest first, plus a first/last pair per pose.

    The comparison only makes sense within a pose -- a front shot against a back
    shot tells you nothing -- so pairing happens per pose rather than across the
    whole album.
    """
    by_pose = []
    for value, label in ProgressPhoto.Pose.choices:
        shots = [p for p in photos if p.pose == value]
        if not shots:
            continue
        chronological = sorted(shots, key=lambda p: p.date)
        by_pose.append(
            {
                "pose": label,
                "pose_value": value,
                "shots": list(reversed(chronological)),
                "first": chronological[0] if len(chronological) >= 2 else None,
                "last": chronological[-1] if len(chronological) >= 2 else None,
                "span_days": (
                    (chronological[-1].date - chronological[0].date).days
                    if len(chronological) >= 2
                    else None
                ),
            }
        )
    return by_pose


def weight_change(measurements):
    """Net weight change from the earliest to the latest entry that has one.

    Returns None unless there are at least two weigh-ins, so the UI shows a
    number only once it means something.
    """
    weighed = [m for m in measurements if m.weight_kg is not None]
    if len(weighed) < 2:
        return None
    chronological = sorted(weighed, key=lambda m: m.date)
    return chronological[-1].weight_kg - chronological[0].weight_kg


class MyProgressView(LoginRequiredMixin, TemplateView):
    """Client-facing progress: measurements, charts, photos, before/after."""

    template_name = "progress/my_progress.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        measurements = list(self.request.user.measurements.all())
        photos = list(self.request.user.progress_photos.all())

        context["measurements"] = measurements
        context["photos"] = photos
        context["photo_count"] = len(photos)
        context["poses"] = photo_timeline(photos)
        context["weight_chart"] = measurement_chart(
            measurements, "weight_kg", label=_("Weight (kg)")
        )
        context["waist_chart"] = measurement_chart(
            measurements, "waist_cm", label=_("Waist (cm)")
        )
        context["records"] = self.request.user.personal_records.select_related(
            "catalog_exercise"
        )
        context["latest"] = measurements[0] if measurements else None
        context["weight_change"] = weight_change(measurements)
        return context


class MeasurementCreateView(LoginRequiredMixin, CreateView):
    model = BodyMeasurement
    form_class = BodyMeasurementForm
    template_name = "progress/measurement_form.html"
    success_url = reverse_lazy("my-progress")

    def form_valid(self, form):
        form.instance.client = self.request.user
        messages.success(self.request, _("Measurements saved."))
        return super().form_valid(form)


class ProgressPhotoCreateView(LoginRequiredMixin, CreateView):
    model = ProgressPhoto
    form_class = ProgressPhotoForm
    template_name = "progress/photo_form.html"
    success_url = reverse_lazy("my-progress")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Show the last shot of each pose so the client can match the framing.
        context["poses"] = photo_timeline(list(self.request.user.progress_photos.all()))
        return context

    def form_valid(self, form):
        form.instance.client = self.request.user
        messages.success(self.request, _("Photo added to your progress."))
        return super().form_valid(form)


class PhotoConsentToggleView(LoginRequiredMixin, UpdateView):
    """Let the client grant or withdraw sharing consent at any time."""

    model = ProgressPhoto
    fields = ["consent_public"]
    template_name = "progress/photo_consent_form.html"
    success_url = reverse_lazy("my-progress")

    def get_queryset(self):
        # Consent is the client's to give: scoped to their own photos only.
        return ProgressPhoto.objects.filter(client=self.request.user)


class PhotoDeleteView(LoginRequiredMixin, DeleteView):
    """A client can always remove a photo of themselves.

    Scoped to their own uploads, and it deletes the file as well as the row --
    leaving the image on disk after someone asks for it to go would defeat the
    point of the consent model.
    """

    model = ProgressPhoto
    template_name = "progress/photo_confirm_delete.html"
    success_url = reverse_lazy("my-progress")

    def get_queryset(self):
        return ProgressPhoto.objects.filter(client=self.request.user)

    def form_valid(self, form):
        stored = self.object.image
        response = super().form_valid(form)
        stored.delete(save=False)
        messages.success(self.request, _("Photo deleted."))
        return response


class PublicResultsView(ListView):
    """Public testimonial page.

    The ``consent_public=True`` filter is the entire point of the consent field.
    Nothing else in the codebase may list photos publicly.
    """

    template_name = "progress/public_results.html"
    context_object_name = "photos"

    def get_queryset(self):
        return (
            ProgressPhoto.objects.filter(consent_public=True)
            .select_related("client")
            .order_by("-date")
        )


# --------------------------------------------------------------------------
# Check-ins
# --------------------------------------------------------------------------


class MyCheckInsView(LoginRequiredMixin, ListView):
    template_name = "progress/my_checkins.html"
    context_object_name = "checkins"

    def get_queryset(self):
        return CheckIn.objects.filter(client=self.request.user)


class CheckInSubmitView(LoginRequiredMixin, UpdateView):
    model = CheckIn
    form_class = CheckInSubmitForm
    template_name = "progress/checkin_form.html"
    success_url = reverse_lazy("my-checkins")

    def get_queryset(self):
        return CheckIn.objects.filter(client=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = context["form"]

        # Last week's shot of the same pose, shown beside each input as a framing
        # reference. Matching the angle is the difference between a comparison
        # and two unrelated photos.
        previous = (
            CheckIn.objects.filter(
                client=self.request.user,
                submitted_at__isnull=False,
                due_date__lt=self.object.due_date,
            )
            .prefetch_related("photos")
            .first()
        )
        reference = (
            {p.pose: p for p in previous.photos.all()} if previous else {}
        )
        existing = {p.pose: p for p in self.object.photos.all()}

        context["photo_slots"] = [
            {
                "field": form[name],
                "reference": reference.get(pose),
                "existing": existing.get(pose),
            }
            for name, pose, _label in POSE_SLOTS
        ]
        context["previous"] = previous
        return context

    @transaction.atomic
    def form_valid(self, form):
        checkin = form.save(commit=False)
        checkin.submitted_at = timezone.now()
        # Re-open it for the coach: editing a reviewed check-in should land back
        # in their queue rather than disappear.
        checkin.reviewed = False
        checkin.save()

        # Photos land in the client's single timeline, tagged with this check-in,
        # so the before/after view and the coach's progress page both see them.
        consent = form.cleaned_data.get("consent_public", False)
        added = 0
        for pose, uploaded in form.photo_uploads():
            ProgressPhoto.objects.update_or_create(
                client=self.request.user,
                checkin=checkin,
                pose=pose,
                defaults={
                    "image": uploaded,
                    "date": checkin.due_date,
                    "consent_public": consent,
                },
            )
            added += 1

        if added:
            messages.success(
                self.request,
                _("Check-in sent with %(count)d photo(s). Your coach will reply soon.")
                % {"count": added},
            )
        else:
            messages.success(self.request, _("Check-in sent to your coach."))
        return redirect(self.success_url)


class CheckInQueueView(AdminRequiredMixin, ListView):
    """Submitted-but-unreviewed check-ins, oldest first."""

    template_name = "progress/checkin_queue.html"
    context_object_name = "checkins"

    def get_queryset(self):
        return (
            CheckIn.objects.filter(submitted_at__isnull=False, reviewed=False)
            .select_related("client")
            .order_by("submitted_at")
        )


class CheckInReplyView(AdminRequiredMixin, UpdateView):
    model = CheckIn
    form_class = CheckInReplyForm
    template_name = "progress/checkin_reply.html"
    success_url = reverse_lazy("checkin-queue")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        checkin = self.object
        client = checkin.client

        # The coach's actual job here is judging change, which needs a baseline.
        # Pair each pose with the same pose from the last submitted check-in.
        previous = (
            CheckIn.objects.filter(
                client=client,
                submitted_at__isnull=False,
                due_date__lt=checkin.due_date,
            )
            .prefetch_related("photos")
            .first()
        )

        current_by_pose = {photo.pose: photo for photo in checkin.photos.all()}
        previous_by_pose = (
            {photo.pose: photo for photo in previous.photos.all()} if previous else {}
        )
        context["photo_pairs"] = [
            {
                "pose": label,
                "then": previous_by_pose.get(value),
                "now": current_by_pose.get(value),
            }
            for value, label in ProgressPhoto.Pose.choices
            if value in current_by_pose or value in previous_by_pose
        ]
        context["previous"] = previous

        measurements = list(client.measurements.all()[:6])
        context["measurements"] = measurements
        context["weight_chart"] = measurement_chart(
            measurements, "weight_kg", label=_("Weight (kg)")
        )
        context["weight_delta"] = _weight_delta(checkin, previous)
        context["adherence"] = workout_services.adherence(client)
        return context

    def form_valid(self, form):
        checkin = form.save(commit=False)
        checkin.replied_at = timezone.now()
        checkin.reviewed = True
        checkin.save()
        messages.success(self.request, _("Reply sent."))
        return redirect(self.success_url)


def _weight_delta(checkin, previous):
    """Change in weight since the previous check-in, or None if incomparable."""
    if not previous or checkin.weight_kg is None or previous.weight_kg is None:
        return None
    return checkin.weight_kg - previous.weight_kg


class CheckInScheduleView(AdminRequiredMixin, CreateView):
    model = CheckIn
    form_class = CheckInScheduleForm
    template_name = "progress/checkin_schedule.html"
    success_url = reverse_lazy("checkin-queue")

    def form_valid(self, form):
        messages.success(self.request, _("Check-in scheduled."))
        return super().form_valid(form)


class ClientProgressView(AdminRequiredMixin, DetailView):
    """Trainer's view of one client's progress."""

    model = User
    template_name = "progress/client_progress.html"
    context_object_name = "client"

    def get_queryset(self):
        return User.objects.filter(role=User.Role.CLIENT)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        measurements = list(self.object.measurements.all())
        photos = list(self.object.progress_photos.all())

        context["measurements"] = measurements
        context["latest"] = measurements[0] if measurements else None
        context["weight_change"] = weight_change(measurements)
        context["weight_chart"] = measurement_chart(
            measurements, "weight_kg", label=_("Weight (kg)")
        )
        context["waist_chart"] = measurement_chart(
            measurements, "waist_cm", label=_("Waist (cm)")
        )
        context["poses"] = photo_timeline(photos)
        context["photo_count"] = len(photos)
        context["checkins"] = self.object.checkins.all()[:10]
        context["adherence"] = workout_services.adherence(self.object)
        return context
