from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from accounts.forms import ProfileForm, SignUpForm, StyledPasswordChangeForm

from .factories import make_employee, make_role, make_staff_user

_LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}


@override_settings(CACHES=_LOCMEM_CACHES)
class SignUpFormTests(TestCase):
    def setUp(self):
        self.employee = make_employee(email="new@example.com", first_name="Jane")

    def form_data(self, **overrides):
        data = {
            "username": "janedoe",
            "email": self.employee.email,
            "password1": "complexpass123!",
            "password2": "complexpass123!",
        }
        data.update(overrides)
        return SignUpForm(data)

    def test_valid_with_matching_employee(self):
        form = self.form_data()
        self.assertTrue(form.is_valid(), form.errors)

    def test_invalid_email_not_in_system(self):
        form = self.form_data(email="unknown@example.com")
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_invalid_email_matches_inactive_employee(self):
        emp = make_employee(email="inactive@example.com")
        emp.is_active = False
        emp.save()
        form = self.form_data(email="inactive@example.com")
        self.assertFalse(form.is_valid())

    def test_case_insensitive_email_match(self):
        form = self.form_data(email="NEW@example.com")
        self.assertTrue(form.is_valid(), form.errors)

    def test_save_creates_inactive_user_and_links(self):
        form = self.form_data()
        form.is_valid()
        user = form.save()
        self.assertFalse(user.is_active)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.user_id, user.pk)
        # name was pulled from employee
        self.assertEqual(user.first_name, "Jane")


@override_settings(CACHES=_LOCMEM_CACHES)
class ProfileFormTests(TestCase):
    def setUp(self):
        self.user = make_staff_user()
        self.employee = make_employee(email=self.user.email)
        self.employee.user = self.user
        self.employee.save()

    def form_data(self, **overrides):
        data = {
            "username": self.user.username,
            "first_name": "New",
            "last_name": "Name",
        }
        data.update(overrides)
        return ProfileForm(data, user=self.user, employee=self.employee)

    def test_initial_values_from_user_and_employee(self):
        form = ProfileForm(user=self.user, employee=self.employee)
        self.assertEqual(form.initial["username"], self.user.username)
        self.assertEqual(form.initial["first_name"], self.employee.first_name)

    def test_save_updates_both_user_and_employee(self):
        form = self.form_data(username="renamed", first_name="New")
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.user.refresh_from_db()
        self.employee.refresh_from_db()
        self.assertEqual(self.user.username, "renamed")
        self.assertEqual(self.employee.first_name, "New")
        # Signal mirrored to user
        self.assertEqual(self.user.first_name, "New")

    def test_duplicate_username_rejected(self):
        User.objects.create_user(username="taken", password="p")
        form = self.form_data(username="taken")
        self.assertFalse(form.is_valid())
        self.assertIn("username", form.errors)

    def test_own_username_allowed(self):
        form = self.form_data(username=self.user.username)
        self.assertTrue(form.is_valid(), form.errors)

    def test_empty_username_rejected(self):
        form = self.form_data(username="  ")
        self.assertFalse(form.is_valid())

    def test_save_without_employee_only_updates_user(self):
        # User without an Employee record
        lonely = make_staff_user("lonely")
        form = ProfileForm(
            {"username": "renamed2", "first_name": "", "last_name": ""},
            user=lonely,
            employee=None,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        lonely.refresh_from_db()
        self.assertEqual(lonely.username, "renamed2")


class PasswordChangeFormTests(TestCase):
    def test_widget_classes_applied(self):
        user = make_staff_user("pwd")
        form = StyledPasswordChangeForm(user)
        for name in ("old_password", "new_password1", "new_password2"):
            self.assertIn("class", form.fields[name].widget.attrs)
