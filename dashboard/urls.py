from django.urls import path
from .views import * #dashboard_view, register_view,items_view,charts_view, tables_view
from django.contrib.auth import views as auth_views
from django.contrib.auth.views import LogoutView


urlpatterns = [
     path(
        "",
        home,
        name="home"
    ),
    path('sources/', source_list, name='source_list'),
    path('sources/add/', add_source, name='add_source'),
    path('sources/edit/<int:pk>/', edit_source, name='edit_source'),
    # path('charts/', charts_view, name='charts'),
    path('tables/', tables_view, name='tables'),
    path('decay_chart/<int:pk>/', decay_chart_view, name='decay_chart'),
    path('auth_signup/', register_view, name='auth_signup'),
    path("save-filter/", save_filter, name="save_filter"),
    path("save-column/", save_column_visibility, name="save_column"),
    path("get-column/", get_column_visibility, name="get_column"),
    path("export-csv/", export_csv),
    path('import-csv/', import_csv, name='import_csv'),
    path("dsrs/image/delete/<int:pk>/", delete_dsrs_image, name="delete_dsrs_image"),
    path("dsrs/<int:pk>/history/", dsrs_history, name="dsrs_history"),
    path("logout/", LogoutView.as_view(), name="logout"),
]