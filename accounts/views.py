from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.models import Group, User
from django.shortcuts import get_object_or_404, redirect, render

from .forms import SignUpForm


def signup(request):
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            form.save()
            return render(request, "registration/signup_pending.html")
    else:
        form = SignUpForm()
    return render(request, "registration/signup.html", {"form": form})


def _pending_users():
    return User.objects.filter(is_active=False, employee__is_active=True)


@login_required
@permission_required("auth.change_user", raise_exception=True)
def pending_accounts(request):
    return render(request, "pending_accounts.html", {"pending": _pending_users()})


@login_required
@permission_required("auth.change_user", raise_exception=True)
def approve_account(request, user_id):
    if request.method == "POST":
        user = get_object_or_404(User, id=user_id)
        user.is_active = True
        user.save()
        staff_group, _ = Group.objects.get_or_create(name="Staff")
        user.groups.add(staff_group)
    return redirect("pending_accounts")
