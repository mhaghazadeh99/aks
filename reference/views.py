from django.shortcuts import render

# Create your views here.



def radionuclide_list(request):

    return render(
        request,
        "reference/radionuclide_list.html"
    )