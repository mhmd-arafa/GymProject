from django.conf import settings
from django.utils import translation


class UserLanguageMiddleware:
    """Apply a signed-in user's saved language preference.

    LocaleMiddleware has already resolved a language from the language cookie or
    the Accept-Language header. For an authenticated user we override that with
    the preference stored on their profile, so the choice follows them across
    devices.

    An explicit switch through ``set_language`` sets LANGUAGE_COOKIE_NAME; we
    treat that cookie as the user acting deliberately and leave it alone. The
    language-switcher view keeps the profile field in step, so the two only
    diverge for a user who has not switched since the field was introduced.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        switched = settings.LANGUAGE_COOKIE_NAME in request.COOKIES

        if user is not None and user.is_authenticated and not switched:
            preferred = getattr(user, "language", "")
            if preferred and preferred != translation.get_language():
                translation.activate(preferred)
                request.LANGUAGE_CODE = preferred

        return self.get_response(request)
