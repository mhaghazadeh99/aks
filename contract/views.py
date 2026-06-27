from django.shortcuts import render,redirect
from django.contrib.auth.decorators import login_required
from .forms import ContractForm
# Create your views here.
from .models import Contract
from django.shortcuts import get_object_or_404
from django.http import HttpResponseForbidden

def contract_index(request):
    contracts = Contract.objects.all().order_by('-created_at')

    return render(request, 'contract/index.html', {
        'contracts': contracts
    })


def contract_edit(request, pk):
    if not request.user.groups.filter(name="Contracts Users").exists():
        return HttpResponseForbidden("No access")
    obj = get_object_or_404(Contract, pk=pk)

    if request.method == "POST":
        form = ContractForm(request.POST, request.FILES, instance=obj)
        if form.is_valid():
            form.save()
            return redirect("contract_index")
    else:
        form = ContractForm(instance=obj)

    return render(request, "contract/contract_edit.html", {"form": form})