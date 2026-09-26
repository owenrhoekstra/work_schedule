from django import forms
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordChangeForm,
    UserCreationForm,
)
from django.contrib.auth.models import User

from schedule.models import Employee


class StyledLoginForm(AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(
            attrs={
                "class": "w-full border border-gray-300 rounded-lg px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-[#FF5A5F]"
            }
        )
    )
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "class": "w-full border border-gray-300 rounded-lg px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-[#FF5A5F]"
            }
        )
    )


class SignUpForm(UserCreationForm):
    email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={
                "class": "w-full border border-gray-300 rounded-lg px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-brand-coral"
            }
        )
    )

    class Meta:
        model = User
        fields = ["username", "email", "password1", "password2"]
        widgets = {
            "username": forms.TextInput(
                attrs={
                    "class": "w-full border border-gray-300 rounded-lg px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-brand-coral"
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style = "w-full border border-gray-300 rounded-lg px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-brand-coral"
        self.fields["password1"].widget.attrs.update({"class": style})
        self.fields["password2"].widget.attrs.update({"class": style})

    def clean_email(self):
        email = self.cleaned_data["email"]
        if not Employee.objects.filter(
            email__iexact=email, user__isnull=True, is_active=True
        ).exists():
            raise forms.ValidationError(
                "This email hasn't been added by management yet."
            )
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_active = False

        employee = Employee.objects.filter(
            email__iexact=self.cleaned_data["email"], is_active=True
        ).first()
        if employee:
            user.first_name = employee.first_name
            user.last_name = employee.last_name

        if commit:
            user.save()

        if employee:
            employee.user = user
            employee.save(update_fields=["user"])

        return user


_PROFILE_INPUT = (
    "w-full border border-gray-300 rounded-lg px-4 py-2.5 "
    "focus:outline-none focus:ring-2 focus:ring-brand-coral"
)


class ProfileForm(forms.Form):
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"class": _PROFILE_INPUT}),
    )
    first_name = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={"class": _PROFILE_INPUT}),
    )
    last_name = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={"class": _PROFILE_INPUT}),
    )

    def __init__(self, *args, user, employee, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.employee = employee
        if not self.is_bound:
            self.initial["username"] = user.username
            if employee:
                self.initial["first_name"] = employee.first_name
                self.initial["last_name"] = employee.last_name

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if not username:
            raise forms.ValidationError("Username cannot be blank.")
        qs = User.objects.filter(username=username).exclude(pk=self.user.pk)
        if qs.exists():
            raise forms.ValidationError("That username is already taken.")
        return username

    def save(self):
        if self.employee:
            self.employee.first_name = self.cleaned_data["first_name"]
            self.employee.last_name = self.cleaned_data["last_name"]
            self.employee.save(update_fields=["first_name", "last_name"])
            # Signal mirrors the name to User automatically
        self.user.username = self.cleaned_data["username"]
        self.user.save(update_fields=["username"])


class StyledPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = _PROFILE_INPUT
