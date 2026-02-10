# core/urls.py
from django.urls import path

from .views import (
    NegociacionAcceptView,
    NegociacionCancelView,
    NegociacionCreateView,
    NegociacionDetailView,
    NegociacionListByReservaView,
    NegociacionRejectView,
    ReservaCancelView,
    ReservaCreateView,
    ReservaDetailView,
    ReservaListView,
)

urlpatterns = [
    # Reservas
    path("reservas", ReservaCreateView.as_view()),                    # POST
    path("reservas/list", ReservaListView.as_view()),                 # GET (por alumno_id o clase_id)
    path("reservas/<int:reserva_id>", ReservaDetailView.as_view()),   # GET
    path("reservas/<int:reserva_id>/cancelar", ReservaCancelView.as_view()),  # PATCH

    # Negociaciones
    path("negociaciones", NegociacionCreateView.as_view()),           # POST
    path("negociaciones/<int:negociacion_id>", NegociacionDetailView.as_view()),  # GET
    path("reservas/<int:reserva_id>/negociaciones", NegociacionListByReservaView.as_view()),  # GET
    path("negociaciones/<int:negociacion_id>/aceptar", NegociacionAcceptView.as_view()),     # PATCH
    path("negociaciones/<int:negociacion_id>/rechazar", NegociacionRejectView.as_view()),    # PATCH
    path("negociaciones/<int:negociacion_id>/cancelar", NegociacionCancelView.as_view()),    # PATCH
]
