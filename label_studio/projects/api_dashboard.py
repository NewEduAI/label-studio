import logging
from collections import defaultdict
from datetime import timedelta

from core.permissions import ViewClassPermission, all_permissions
from django.db.models import Avg, Count, F, Q
from django.db.models.functions import TruncDate
from django.utils import timezone
from projects.models import Project
from rest_framework import generics
from rest_framework.parsers import JSONParser
from rest_framework.response import Response

logger = logging.getLogger(__name__)


class ProjectDashboardAPI(generics.RetrieveAPIView):
    """Project-level dashboard with completion stats, label distribution,
    annotator performance, and daily activity timeline."""

    permission_required = ViewClassPermission(GET=all_permissions.projects_view)
    queryset = Project.objects.all()

    def retrieve(self, request, *args, **kwargs):
        project = self.get_object()
        days = int(request.query_params.get('days', 30))
        since = timezone.now() - timedelta(days=days)

        from tasks.models import Annotation, Task

        total_tasks = Task.objects.filter(project=project).count()
        labeled_tasks = Task.objects.filter(project=project, is_labeled=True).count()
        total_annotations = Annotation.objects.filter(project=project).count()

        label_distribution = {}
        try:
            summary = project.summary
            label_distribution = summary.created_labels or {}
        except Exception:
            pass

        annotator_stats = list(
            Annotation.objects.filter(project=project, created_at__gte=since)
            .values(
                annotator_id=F('completed_by__id'),
                annotator_email=F('completed_by__email'),
                annotator_first_name=F('completed_by__first_name'),
                annotator_last_name=F('completed_by__last_name'),
            )
            .annotate(
                annotation_count=Count('id'),
                avg_lead_time=Avg('lead_time'),
            )
            .order_by('-annotation_count')
        )

        timeline = list(
            Annotation.objects.filter(project=project, created_at__gte=since)
            .annotate(date=TruncDate('created_at'))
            .values('date')
            .annotate(count=Count('id'))
            .order_by('date')
        )
        timeline_data = [
            {'date': entry['date'].isoformat(), 'count': entry['count']}
            for entry in timeline
        ]

        return Response({
            'overview': {
                'total_tasks': total_tasks,
                'labeled_tasks': labeled_tasks,
                'unlabeled_tasks': total_tasks - labeled_tasks,
                'total_annotations': total_annotations,
                'completion_percentage': round(
                    (labeled_tasks / total_tasks * 100) if total_tasks > 0 else 0, 1
                ),
            },
            'label_distribution': label_distribution,
            'annotator_stats': [
                {
                    'user_id': stat['annotator_id'],
                    'email': stat['annotator_email'],
                    'name': f"{stat['annotator_first_name'] or ''} {stat['annotator_last_name'] or ''}".strip()
                    or stat['annotator_email'],
                    'annotation_count': stat['annotation_count'],
                    'avg_lead_time_seconds': round(stat['avg_lead_time'], 1) if stat['avg_lead_time'] else None,
                }
                for stat in annotator_stats
            ],
            'timeline': timeline_data,
            'period_days': days,
        })
