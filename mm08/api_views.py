from datetime import datetime
from django.utils.dateparse import parse_datetime
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, mixins
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination

from .models import Instrument, Candle
from .serializers import InstrumentSerializer, CandleSerializer


class DefaultPagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = "page_size"
    max_page_size = 2000


class InstrumentViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Instrument.objects.all().order_by("ticker")
    serializer_class = InstrumentSerializer
    pagination_class = DefaultPagination


class CandleViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = CandleSerializer
    pagination_class = DefaultPagination

    def get_queryset(self):
        qs = Candle.objects.select_related("instrument").all().order_by("-dt")
        ticker = self.request.query_params.get("ticker")
        if ticker:
            qs = qs.filter(instrument__ticker=ticker.upper())
        interval = self.request.query_params.get("interval")
        if interval:
            qs = qs.filter(interval=int(interval))
        date_from = self.request.query_params.get("from")
        date_to = self.request.query_params.get("to")

        # поддерживаем YYYY-MM-DD или полные ISO-даты
        if date_from:
            try:
                if len(date_from) == 10:
                    date_from = datetime.fromisoformat(date_from + " 00:00:00")
                else:
                    date_from = parse_datetime(date_from)
                qs = qs.filter(dt__gte=date_from)
            except Exception:
                pass
        if date_to:
            try:
                if len(date_to) == 10:
                    date_to = datetime.fromisoformat(date_to + " 23:59:59")
                else:
                    date_to = parse_datetime(date_to)
                qs = qs.filter(dt__lte=date_to)
            except Exception:
                pass

        limit = self.request.query_params.get("limit")
        qs = qs.order_by("-dt")
        if limit:
            try:
                qs = qs[:min(int(limit), 10000)]
            except ValueError:
                pass
        return qs


    @action(detail=False, methods=["get"])
    def latest(self, request):
        """Быстрый доступ к последней свече по тикеру/интервалу."""
        ticker = request.query_params.get("ticker")
        interval = request.query_params.get("interval")
        if not ticker:
            return Response({"detail": "ticker is required"}, status=400)
        qs = Candle.objects.filter(instrument__ticker=ticker.upper())
        if interval:
            qs = qs.filter(interval=int(interval))
        obj = qs.order_by("-dt").first()
        if not obj:
            return Response({"detail": "not found"}, status=404)
        return Response(CandleSerializer(obj).data)
