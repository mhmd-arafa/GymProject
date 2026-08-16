from django.contrib.auth.forms import UserCreationForm
from .models import User
from django import forms

class ClientRegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ["username", "email", "password1", "password2"]

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.CLIENT
        if commit:
            user.save()
        return user