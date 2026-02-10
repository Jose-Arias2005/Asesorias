from django.urls import path
from .views import (
    MateriaSuggestView,
    ClaseCreateView, ClaseDetailView, ClaseEstadoUpdateView, ClaseSearchView,
    CalificacionCreateView, CalificacionDeleteView,
    LlevoUpsertView,
)

urlpatterns = [
    path("materias/suggest", MateriaSuggestView.as_view()),

    path("clases", ClaseCreateView.as_view()),
    path("clases/<int:clase_id>", ClaseDetailView.as_view()),
    path("clases/<int:clase_id>/estado", ClaseEstadoUpdateView.as_view()),
    path("clases/search", ClaseSearchView.as_view()),

    path("calificaciones", CalificacionCreateView.as_view()),
    path("calificaciones/delete", CalificacionDeleteView.as_view()),

    path("llevo", LlevoUpsertView.as_view()),
]
