from django.urls import path
from apps.facilities.views.map_editor import MapEditorObjectsView, MapEditorSaveView

urlpatterns = [
    path(
        "map-editor/objects/", MapEditorObjectsView.as_view(), name="map-editor-objects"
    ),
    path("map-editor/save/", MapEditorSaveView.as_view(), name="map-editor-save"),
]
