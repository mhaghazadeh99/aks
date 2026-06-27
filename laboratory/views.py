from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required

from .models import Sample, Analysis
from .forms import SampleForm, AnalysisForm, GammaActivityForm,SampleCreateForm
from django.utils import timezone
from waste.models import WasteBatch

@login_required
def sample_create(request, batch_id):

    batch = get_object_or_404(
        WasteBatch,
        pk=batch_id
    )

    if request.method == 'POST':

        form = SampleCreateForm(request.POST)

        if form.is_valid():

            sample = form.save(commit=False)

            sample.batch = batch
            sample.collected_by = request.user

            sample.save()

            return redirect(
                'waste_detail',
                pk=batch.id
            )

    else:

        form = SampleCreateForm()

    return render(
        request,
        'laboratory/sample_create.html',
        {
            'form': form,
            'batch': batch
        }
    )
# ---------------------------
# laboratory Queue
# ---------------------------
@login_required
def lab_queue(request):

    samples = Sample.objects.exclude(status='COMPLETED').order_by('-urgent','sampling_date')

    return render(request, 'laboratory/queue.html', {
        'samples': samples
    })


# ---------------------------
# Enter Analysis
# ---------------------------
@login_required
def analysis_create(request, sample_id):

    sample = get_object_or_404(Sample, id=sample_id)

    if request.method == "POST":
        form = AnalysisForm(request.POST)

        if form.is_valid():
            analysis = form.save(commit=False)
            analysis.sample = sample
            analysis.analyst = request.user
            analysis.save()

            sample.status = 'COMPLETED'
            sample.save()

            return redirect('lab_queue')

    else:
        form = AnalysisForm()

    return render(request, 'laboratory/analysis_form.html', {
        'form': form,
        'sample': sample
    })


@login_required
def receive_sample_lab(request, sample_id):

    sample = get_object_or_404(
        Sample,
        pk=sample_id
    )

    sample.status = 'RECEIVED_BY_LAB'

    sample.lab_received_date = timezone.now().date()

    sample.save()

    return redirect('lab_queue')