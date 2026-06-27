from django.shortcuts import render

# Create your views here.
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required

from .models import WasteBatch
from .forms import WasteBatchForm


# ---------------------------
# Create Waste Batch
# ---------------------------
@login_required
def waste_create(request):

    if request.method == "POST":
        form = WasteBatchForm(request.POST, request.FILES)

        if form.is_valid():
            batch = form.save(commit=False)
            batch.created_by = request.user
            batch.save()
            return redirect('waste_detail', batch.id)

    else:
        form = WasteBatchForm()

    return render(request, 'waste/create.html', {'form': form})


# ---------------------------
# Waste Detail
# ---------------------------
@login_required
def waste_detail(request, pk):

    batch = get_object_or_404(WasteBatch, pk=pk)

    return render(request, 'waste/detail.html', {
        'batch': batch
    })


# ---------------------------
# Waste List
# ---------------------------
@login_required
def waste_list(request):

    batches = WasteBatch.objects.filter(is_active=True)

    return render(request, 'waste/list.html', {
        'batches': batches
    })