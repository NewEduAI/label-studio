"""This file and its contents are licensed under the Apache License 2.0. Please see the included NOTICE for copyright information and LICENSE for a copy of the license."""

import logging

from organizations.models import OrganizationMember
from projects.models import Project, ProjectMember
from projects.serializers import ProjectMemberCreateSerializer, ProjectMemberSerializer
from rest_framework import generics, status
from rest_framework.generics import get_object_or_404
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from label_studio.core.permissions import ViewClassPermission, all_permissions

logger = logging.getLogger(__name__)


class ProjectMemberPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'


class ProjectMemberListAPI(generics.ListCreateAPIView):
    """List project members or add a new member to the project."""

    parser_classes = (JSONParser, FormParser, MultiPartParser)
    permission_required = ViewClassPermission(
        GET=all_permissions.projects_change,
        POST=all_permissions.projects_change,
    )
    pagination_class = ProjectMemberPagination

    def get_project(self):
        return get_object_or_404(Project, pk=self.kwargs['pk'])

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ProjectMemberCreateSerializer
        return ProjectMemberSerializer

    def get_queryset(self):
        project = self.get_project()
        return ProjectMember.objects.filter(
            project=project, enabled=True
        ).select_related('user').order_by('created_at')

    def create(self, request, *args, **kwargs):
        project = self.get_project()
        serializer = ProjectMemberCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_id = serializer.validated_data['user_id']
        role = serializer.validated_data['role']

        org = project.organization
        if not OrganizationMember.objects.filter(
            organization=org, user_id=user_id, deleted_at__isnull=True
        ).exists():
            return Response(
                {'detail': 'User is not a member of this organization'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        member, created = ProjectMember.objects.get_or_create(
            project=project,
            user_id=user_id,
            defaults={'role': role, 'enabled': True},
        )
        if not created:
            member.role = role
            member.enabled = True
            member.save(update_fields=['role', 'enabled', 'updated_at'])

        return Response(
            ProjectMemberSerializer(member).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class ProjectMemberDetailAPI(generics.RetrieveUpdateDestroyAPIView):
    """Update or remove a project member."""

    parser_classes = (JSONParser, FormParser, MultiPartParser)
    permission_required = ViewClassPermission(
        GET=all_permissions.projects_change,
        PATCH=all_permissions.projects_change,
        DELETE=all_permissions.projects_change,
    )
    serializer_class = ProjectMemberSerializer

    def get_project(self):
        return get_object_or_404(Project, pk=self.kwargs['pk'])

    def get_queryset(self):
        project = self.get_project()
        return ProjectMember.objects.filter(project=project).select_related('user')

    def get_object(self):
        queryset = self.get_queryset()
        return get_object_or_404(queryset, pk=self.kwargs['member_pk'])

    def patch(self, request, pk=None, member_pk=None):
        member = self.get_object()
        new_role = request.data.get('role')
        if new_role and new_role in dict(ProjectMember.ProjectRoleChoices.choices):
            member.role = new_role
            member.save(update_fields=['role', 'updated_at'])
        serializer = self.get_serializer(member)
        return Response(serializer.data)

    def delete(self, request, pk=None, member_pk=None):
        member = self.get_object()
        member.enabled = False
        member.save(update_fields=['enabled', 'updated_at'])
        return Response(status=status.HTTP_204_NO_CONTENT)
