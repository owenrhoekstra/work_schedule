from django import forms
from django.utils import timezone

from .models import Employee, Role, Title

_INPUT_CLASS = (
    "w-full border border-gray-300 rounded-lg px-3 py-2 "
    "focus:outline-none focus:ring-2 focus:ring-brand-coral"
)


class EmployeeForm(forms.ModelForm):
    """Create/edit an Employee.

    `company=` scopes the `title` and `role` querysets to the current
    tenant. Without it, a manager of company A could assign a role
    belonging to company B. The caller passes `company=` for new
    employees; edits auto-detect from `instance.company_id`.
    """

    class Meta:
        model = Employee
        fields = ["title", "first_name", "last_name", "role", "email", "start_date"]
        widgets = {
            "title": forms.Select(attrs={"class": _INPUT_CLASS}),
            "first_name": forms.TextInput(attrs={"class": _INPUT_CLASS}),
            "last_name": forms.TextInput(attrs={"class": _INPUT_CLASS}),
            "role": forms.Select(attrs={"class": _INPUT_CLASS}),
            "email": forms.EmailInput(attrs={"class": _INPUT_CLASS}),
            "start_date": forms.DateInput(
                attrs={"class": _INPUT_CLASS, "type": "date"}
            ),
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company is None and self.instance.company_id:
            company = self.instance.company
        self.company = company
        if company:
            self.fields["title"].queryset = Title.objects.filter(company=company)
            self.fields["role"].queryset = Role.objects.filter(company=company)
        else:
            self.fields["title"].queryset = Title.objects.none()
            self.fields["role"].queryset = Role.objects.none()
        self.fields["title"].required = False
        self.fields["title"].empty_label = "—"

    def clean_email(self):
        email = self.cleaned_data["email"]
        qs = Employee.objects.filter(email__iexact=email)
        if self.company:
            qs = qs.filter(company=self.company)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)

        existing = qs.first()
        if not existing:
            return email

        if existing.last_day and existing.last_day < timezone.localdate():
            raise forms.ValidationError(
                f"This email belongs to a former employee ({existing}). "
                f"Reactivate them from Settings → Former employees instead."
            )

        raise forms.ValidationError("Another employee already uses this email.")
