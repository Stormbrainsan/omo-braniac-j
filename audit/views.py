from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated

from .filters import AuditLogFilter
from .models import AuditLog
from .serializers import AuditLogSerializer


class AuditLogListView(ListAPIView):
    """
    GET /api/v1/audit/logs

    JWT-authenticated, paginated, filterable by email/event/from/to,
    newest first (the model's default ordering already does this).
    """

    queryset = AuditLog.objects.all()
    serializer_class = AuditLogSerializer
    permission_classes = [IsAuthenticated]
    filterset_class = AuditLogFilter

    @extend_schema(
        parameters=[
            OpenApiParameter("email", str, description="Exact match, case-insensitive."),
            OpenApiParameter(
                "event", str, description="One of the AuditLog.Event choices."
            ),
            OpenApiParameter(
                "from", str, description="ISO-8601 datetime, inclusive lower bound."
            ),
            OpenApiParameter(
                "to", str, description="ISO-8601 datetime, inclusive upper bound."
            ),
        ]
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)
