from django.urls import path
from . import views

urlpatterns = [

    path("", views.receiving_home, name="receiving_home"),
    path("list/", views.receive_list, name="receive_list"),

    # Queues
    path("queue/manager-input/", views.manager_input_queue, name="receive_manager_input_queue"),
    path("queue/manager/", views.manager_queue, name="receive_manager_queue"),
    path("queue/control/", views.control_queue, name="receive_control_queue"),
    path("queue/deputy/", views.deputy_queue, name="receive_deputy_queue"),
    path("queue/ceo/", views.ceo_queue, name="receive_ceo_queue"),
    path("queue/contracts/", views.contracts_queue, name="receive_contracts_queue"),
    path("queue/finance/", views.finance_queue, name="receive_finance_queue"),
    path("queue/receiving/", views.receiving_queue, name="receive_receiving_queue"),

    # Create / edit draft
    path("new/", views.receive_create, name="receive_create"),
    path("<int:pk>/edit/", views.receive_create, name="receive_create_edit"),

    # Sources (coordinator)
    path("<int:pk>/sources/", views.receive_add_sources, name="receive_add_sources"),
    path("<int:pk>/sources/finish/", views.receive_finish_sources, name="receive_finish_sources"),

    # Manager data entry
    path("<int:pk>/manager-input/", views.receive_manager_input, name="receive_manager_input"),
    path("<int:pk>/manager-input/control-add/", views.receive_control_add, name="receive_control_add"),
    path("<int:pk>/manager-input/done/", views.receive_manager_input_done, name="receive_manager_input_done"),

    # Signing
    path("<int:pk>/sign/", views.receive_sign, name="receive_sign"),

    # Contract
    path("<int:pk>/contract/new/", views.receive_contract_create, name="receive_contract_create"),
    path("contract/<int:pk>/edit/", views.receive_contract_update, name="receive_contract_update"),

    # Finance
    path("<int:pk>/payment/", views.receive_payment_update, name="receive_payment_update"),

    # Receiving / characterization
    path("<int:pk>/characterization/", views.receive_characterization, name="receive_characterization"),
    path(
        "<int:pk>/characterization/<int:dsrs_pk>/",
        views.dsrs_characterization_update,
        name="dsrs_characterization_update",
    ),
    path(
        "<int:pk>/characterization/<int:dsrs_pk>/mark-stored/",
        views.dsrs_mark_stored,
        name="dsrs_mark_stored",
    ),

    # Detail
    path("<int:pk>/", views.receive_detail, name="receive_detail"),
]