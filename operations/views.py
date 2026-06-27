from django.shortcuts import render

# Create your views here.
from django.db import transaction
from django.shortcuts import render, redirect

from waste.models import WasteBatch
from .models import Operation, OperationInput, OperationOutput
from django.contrib.auth.decorators import login_required

@login_required
def merge_operation(request):

    batches = WasteBatch.objects.filter(is_active=True)

    if request.method == "POST":

        selected_ids = request.POST.getlist('batches')
        new_id = request.POST.get('new_batch_id')

        with transaction.atomic():

            op = Operation.objects.create(
                operation_number=f"MERGE-{new_id}",
                operation_type="MERGE",
                operation_date=request.POST.get('date'),
                created_by=request.user
            )

            new_batch = WasteBatch.objects.create(
                waste_id=new_id,
                waste_type=batches.first().waste_type,
                facility=batches.first().facility,
                origin_of_waste="PROCESSING",
                date_received=request.POST.get('date'),
                created_by=request.user
            )

            OperationOutput.objects.create(
                operation=op,
                batch=new_batch
            )

            for b in WasteBatch.objects.filter(id__in=selected_ids):

                OperationInput.objects.create(
                    operation=op,
                    batch=b,
                    mass_used_kg=b.mass_kg,
                    volume_used_m3=b.volume_m3
                )

                b.is_active = False
                b.save()

        return redirect('waste_list')

    return render(request, 'operations/merge.html', {
        'batches': batches
    })


@login_required
def split_operation(request, batch_id):

    batch = WasteBatch.objects.get(id=batch_id)

    if request.method == "POST":

        parts = request.POST.getlist('parts')  # JSON-like input simplified

        with transaction.atomic():

            op = Operation.objects.create(
                operation_number=f"SPLIT-{batch.waste_id}",
                operation_type="SPLIT",
                operation_date=request.POST.get('date'),
                created_by=request.user
            )

            OperationInput.objects.create(
                operation=op,
                batch=batch,
                mass_used_kg=batch.mass_kg,
                volume_used_m3=batch.volume_m3
            )

            for p in parts:

                child = WasteBatch.objects.create(
                    waste_id=p,
                    waste_type=batch.waste_type,
                    facility=batch.facility,
                    origin_of_waste="PROCESSING",
                    date_received=request.POST.get('date'),
                    mass_kg=batch.mass_kg,
                    volume_m3=batch.volume_m3,
                    created_by=request.user
                )

                OperationOutput.objects.create(
                    operation=op,
                    batch=child
                )

            batch.is_active = False
            batch.save()

        return redirect('waste_list')

    return render(request, 'operations/split.html', {
        'batch': batch
    })