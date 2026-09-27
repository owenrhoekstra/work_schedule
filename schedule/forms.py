from datetime import date

from django import forms

from .models import Employee, Role, Title

_INPUT_CLASS = (
    "w-full border border-gray-300 rounded-lg px-3 py-2 "
    "focus:outline-none focus:ring-2 focus:ring-brand-coral"
)


class EmployeeForm(forms.ModelForm):
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"].queryset = Title.objects.all()
        self.fields["role"].queryset = Role.objects.all()
        self.fields["title"].required = False
        self.fields["title"].empty_label = "—"

    def clean_email(self):
        email = self.cleaned_data["email"]
        qs = Employee.objects.filter(email__iexact=email)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)

        existing = qs.first()
        if not existing:
            return email

        if existing.inactivated_on and existing.inactivated_on <= date.today():
            raise forms.ValidationError(
                f"This email belongs to a former employee ({existing}). "
                f"Reactivate them from Settings → Former employees instead."
            )

        raise forms.ValidationError("Another employee already uses this email.")
