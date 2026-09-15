import django_filters

from .models import AuditLog


class AuditLogFilter(django_filters.FilterSet):
    email = django_filters.CharFilter(field_name="email", lookup_expr="iexact")
    event = django_filters.ChoiceFilter(field_name="event", choices=AuditLog.Event.choices)

    # The brief asks for query params literally named `from` / `to`, but
    # `from` is a reserved word in Python and can't be a class attribute
    # name. We declare them as `from_date`/`to_date` here, then patch
    # `base_filters` directly below to rename the exposed query param keys
    # after the FilterSet class has already built its declared filters.
    from_date = django_filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")
    to_date = django_filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = AuditLog
        fields = ["email", "event", "from_date", "to_date"]


# Expose the actual query params as `from` / `to` per the spec, while
# keeping valid Python identifiers everywhere else in the code.
AuditLogFilter.base_filters["from"] = AuditLogFilter.base_filters.pop("from_date")
AuditLogFilter.base_filters["to"] = AuditLogFilter.base_filters.pop("to_date")
