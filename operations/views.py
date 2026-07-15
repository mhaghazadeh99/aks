from django.shortcuts import render


def operations_home(request):

    return render(
        request,
        "operations/operations_home.html",
    )